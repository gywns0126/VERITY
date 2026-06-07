#!/usr/bin/env python3
"""
미장 관측 로깅 v0 — AAII / NAAIM / FINRA 공매도 / SEC Form4 내부자.

⚠️ 관측 ONLY — 점수/결정 wire 0. data/observations/us_market_signals.jsonl append-only.
   승격(점수 편입)은 사전등록 통과 후 "하나씩" ([[project_observation_scoring_prereg_queue]]).
   동시 투입 금지 — 다중검정(multiple testing) 희석 + DSR 임계 상승 ([[feedback_methodology_pre_registration]]).
   결정 룰 단순 / 로깅 풍부 직교 ([[feedback_decision_logging_separation]]).

각 소스 실호출 검증 완료 (2026-06-07):
  · AAII   : aaii.com/sentimentsurvey (브라우저 UA 필수, 봇 UA=403). 페이지 데이터
             테이블 "Bullish Neutral Bearish {date} b% n% bear%" 최신행 = 현재주차.
             주의: 같은 페이지에 1년 High / 장기평균도 있음 — 첫 데이터행만 타겟 + 합≈100 검증.
  · NAAIM  : naaim.org 페이지 → USE_Data-since-Inception_*.xlsx 링크(매주 갱신) → 'Mean/Average' 열.
  · FINRA  : cdn.finra.org/equity/regsho/daily/CNMSshvol{YYYYMMDD}.txt (거래일별, pipe).
             시장 aggregate = ΣShortVolume / ΣTotalVolume.
  · Form4  : sec.gov/files/company_tickers.json (ticker→CIK) + data.sec.gov/submissions/CIK{10}.json
             → form=='4' 최근분 → form4.xml transactionCode P(매수)/S(매도). 유니버스 scoped.

grain = 시장 레벨 aggregate (regime 신호, market_horizon family 정합). 종목별은 점수화 단계.
방어: 소스별 graceful (실패 시 해당 source None → skip, 전체 run 은 진행).
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

from api.config import DATA_DIR, now_kst

logger = logging.getLogger(__name__)

OBS_DIR = os.path.join(DATA_DIR, "observations")
OBS_PATH = os.path.join(OBS_DIR, "us_market_signals.jsonl")

_BROWSER_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
               "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120 Safari/537.36")
_SEC_UA = "VERITY/1.0 (gywns0126@gmail.com)"  # SEC 는 연락처 포함 UA 요구

AAII_URL = "https://www.aaii.com/sentimentsurvey"
NAAIM_PAGE = "https://naaim.org/programs/naaim-exposure-index/"
FINRA_TMPL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{ymd}.txt"
SEC_TICKERS = "https://www.sec.gov/files/company_tickers.json"
SEC_SUBMISSIONS = "https://data.sec.gov/submissions/CIK{cik10}.json"

FORM4_UNIVERSE_CAP = 40    # US 유니버스 상한 (cost cap)
FORM4_PER_TICKER = 8       # 종목당 최근 Form4 분류 상한 (유니버스 균등 커버, 앞쪽 편중 방지)
FORM4_XML_CAP = 200        # 글로벌 안전 상한 (runaway 방지)
FORM4_LOOKBACK_DAYS = 30


# ── AAII ────────────────────────────────────────────────────────────────
def _parse_aaii(html_text: str) -> Optional[Dict[str, Any]]:
    """AAII 페이지 → 현재주차 trio. 데이터 테이블 첫 행만 타겟 + 합≈100 검증
    (같은 페이지의 1년 High / 장기평균 오인 차단)."""
    plain = re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html_text))
    m = re.search(
        r"Bullish\s+Neutral\s+Bearish\s+(\d{1,2}/\d{1,2}/\d{4})\s+"
        r"(\d{1,2}\.\d)%\s+(\d{1,2}\.\d)%\s+(\d{1,2}\.\d)%",
        plain,
    )
    if not m:
        logger.warning("AAII 데이터 테이블 미발견 — 형식 변경 의심")
        return None
    date_s, bull, neu, bear = m.group(1), float(m.group(2)), float(m.group(3)), float(m.group(4))
    if not (95.0 <= bull + neu + bear <= 105.0):  # 합≈100 검증
        logger.warning("AAII 합 %.1f != 100 — 파싱 오인 의심, skip", bull + neu + bear)
        return None
    mm, dd, yy = date_s.split("/")
    return {
        "source": "aaii", "period": f"{yy}-{int(mm):02d}-{int(dd):02d}",
        "metrics": {"bullish": bull, "neutral": neu, "bearish": bear,
                    "bull_bear_spread": round(bull - bear, 1)},
    }


def fetch_aaii(session: Optional[requests.Session] = None) -> Optional[Dict[str, Any]]:
    sess = session or requests.Session()
    try:
        r = sess.get(AAII_URL, headers={"User-Agent": _BROWSER_UA}, timeout=15)
        if r.status_code != 200:
            logger.warning("AAII HTTP %s", r.status_code)
            return None
        return _parse_aaii(r.text)
    except (requests.RequestException, ValueError) as e:
        logger.warning("AAII 실패: %s", e)
        return None


# ── NAAIM ───────────────────────────────────────────────────────────────
def fetch_naaim(session: Optional[requests.Session] = None) -> Optional[Dict[str, Any]]:
    sess = session or requests.Session()
    try:
        import openpyxl  # graceful: 미설치 시 NAAIM 만 skip
    except ImportError:
        logger.warning("openpyxl 미설치 — NAAIM skip")
        return None
    try:
        pg = sess.get(NAAIM_PAGE, headers={"User-Agent": _SEC_UA}, timeout=15)
        xm = re.search(r"https?://[^\"']*USE_Data[^\"']*\.xlsx", pg.text)
        if not xm:
            logger.warning("NAAIM xlsx 링크 미발견")
            return None
        xlsx = sess.get(xm.group(0), headers={"User-Agent": _SEC_UA}, timeout=25)
        if xlsx.status_code != 200:
            logger.warning("NAAIM xlsx HTTP %s", xlsx.status_code)
            return None
        wb = openpyxl.load_workbook(io.BytesIO(xlsx.content), read_only=True)
        ws = wb.active
        header = None
        latest_date = None
        latest_val = None
        for row in ws.iter_rows(values_only=True):
            if header is None:
                header = [str(c).strip() if c is not None else "" for c in row]
                try:
                    di = header.index("Date")
                    vi = next(i for i, h in enumerate(header) if h in ("Mean/Average", "Mean", "Average"))
                except (ValueError, StopIteration):
                    logger.warning("NAAIM 헤더 형식 변경: %s", header[:6])
                    return None
                continue
            d, v = row[di], row[vi]
            if isinstance(d, datetime) and isinstance(v, (int, float)):
                if latest_date is None or d > latest_date:
                    latest_date, latest_val = d, float(v)
        if latest_date is None:
            return None
        return {
            "source": "naaim", "period": latest_date.strftime("%Y-%m-%d"),
            "metrics": {"exposure_mean": round(latest_val, 2)},
        }
    except (requests.RequestException, ValueError) as e:
        logger.warning("NAAIM 실패: %s", e)
        return None


# ── FINRA 공매도 (시장 aggregate) ────────────────────────────────────────
def _last_trading_ymd(asof: datetime) -> str:
    d = asof
    while d.weekday() >= 5:  # 토(5)/일(6) → 직전 금
        d -= timedelta(days=1)
    return d.strftime("%Y%m%d")


def fetch_finra_short(asof: datetime, session: Optional[requests.Session] = None) -> Optional[Dict[str, Any]]:
    sess = session or requests.Session()
    # 거래일 파일이 아직 없을 수 있어 최대 5거래일 역행 시도
    d = asof
    for _ in range(7):
        ymd = _last_trading_ymd(d)
        try:
            r = sess.get(FINRA_TMPL.format(ymd=ymd), headers={"User-Agent": _SEC_UA}, timeout=15)
            if r.status_code == 200 and r.text.startswith("Date|"):
                tot_short = 0.0
                tot_all = 0.0
                n = 0
                for line in r.text.splitlines()[1:]:
                    parts = line.split("|")
                    if len(parts) < 5:
                        continue
                    try:
                        tot_short += float(parts[2])
                        tot_all += float(parts[4])
                        n += 1
                    except ValueError:
                        continue
                if tot_all <= 0 or n == 0:
                    return None
                ratio = round(tot_short / tot_all * 100, 2)
                return {
                    "source": "finra_short", "period": f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}",
                    "metrics": {"market_short_volume_pct": ratio, "n_symbols": n},
                }
        except requests.RequestException as e:
            logger.warning("FINRA %s 실패: %s", ymd, e)
        d -= timedelta(days=1)
    logger.warning("FINRA 최근 7일 내 파일 미발견")
    return None


# ── SEC Form4 내부자 (유니버스 scoped) ───────────────────────────────────
def _us_universe() -> List[str]:
    try:
        with open(os.path.join(DATA_DIR, "portfolio.json"), encoding="utf-8") as f:
            p = json.load(f)
    except (OSError, ValueError):
        return []
    out = set()
    for key in ("recommendations", "candidates"):
        for s in (p.get(key) or []):
            if s.get("currency") == "USD" and s.get("ticker"):
                out.add(str(s["ticker"]).upper())
    return sorted(out)[:FORM4_UNIVERSE_CAP]


def _ticker_cik_map(sess: requests.Session) -> Dict[str, str]:
    r = sess.get(SEC_TICKERS, headers={"User-Agent": _SEC_UA}, timeout=15)
    r.raise_for_status()
    out = {}
    for row in r.json().values():
        out[str(row["ticker"]).upper()] = f"{int(row['cik_str']):010d}"
    return out


def _classify_form4_xml(sess: requests.Session, cik: str, accn: str, primary_doc: str) -> Optional[str]:
    """form4.xml transactionCode 분류 → 'buy'(P 포함) / 'sell'(S 만) / None."""
    accn_nodash = accn.replace("-", "")
    raw_doc = primary_doc.split("/")[-1]  # 'xslF345X06/form4.xml' → 'form4.xml'
    url = f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accn_nodash}/{raw_doc}"
    try:
        r = sess.get(url, headers={"User-Agent": _SEC_UA}, timeout=12)
        if r.status_code != 200:
            return None
        root = ET.fromstring(r.text)
        codes = [e.text for e in root.iter("transactionCode") if e.text]
        if not codes:
            return None
        if "P" in codes:
            return "buy"
        if "S" in codes:
            return "sell"
        return "other"  # A(증여)/M(옵션행사) 등 — 방향 신호 약함
    except (requests.RequestException, ET.ParseError):
        return None


def fetch_insider_form4(asof: datetime, session: Optional[requests.Session] = None) -> Optional[Dict[str, Any]]:
    sess = session or requests.Session()
    tickers = _us_universe()
    if not tickers:
        logger.warning("US 유니버스 0 — Form4 skip")
        return None
    try:
        cik_map = _ticker_cik_map(sess)
    except (requests.RequestException, ValueError) as e:
        logger.warning("SEC ticker map 실패: %s", e)
        return None
    cutoff = (asof - timedelta(days=FORM4_LOOKBACK_DAYS)).strftime("%Y-%m-%d")
    buys = sells = others = unclassified = 0
    xml_fetched = 0
    covered = 0
    for tkr in tickers:
        cik = cik_map.get(tkr)
        if not cik:
            continue
        try:
            sub = sess.get(SEC_SUBMISSIONS.format(cik10=cik), headers={"User-Agent": _SEC_UA}, timeout=12)
            time.sleep(0.12)  # SEC 10 req/s
            if sub.status_code != 200:
                continue
            rec = sub.json().get("filings", {}).get("recent", {})
            forms = rec.get("form", [])
            dates = rec.get("filingDate", [])
            accns = rec.get("accessionNumber", [])
            pdocs = rec.get("primaryDocument", [""] * len(forms))
            covered += 1
            per_ticker = 0
            for i in range(len(forms)):
                if forms[i] != "4" or dates[i] < cutoff:
                    continue
                if per_ticker >= FORM4_PER_TICKER or xml_fetched >= FORM4_XML_CAP:
                    break
                kind = _classify_form4_xml(sess, cik, accns[i], pdocs[i])
                xml_fetched += 1
                per_ticker += 1
                time.sleep(0.12)
                if kind == "buy":
                    buys += 1
                elif kind == "sell":
                    sells += 1
                elif kind == "other":
                    others += 1
                else:
                    unclassified += 1
        except (requests.RequestException, ValueError):
            continue
    classified = buys + sells
    return {
        "source": "insider_form4",
        "period": asof.strftime("%Y-%m-%d"),
        "metrics": {
            "lookback_days": FORM4_LOOKBACK_DAYS,
            "universe_covered": covered,
            "buy_filings": buys,
            "sell_filings": sells,
            "other_filings": others,
            "net_buy_minus_sell": buys - sells,
            "buy_ratio": round(buys / classified, 3) if classified else None,
            "xml_fetched": xml_fetched,
            "capped": xml_fetched >= FORM4_XML_CAP,
        },
    }


# ── 관측 로그 append (dedupe by source+period) ───────────────────────────
def _existing_keys() -> set:
    keys = set()
    if not os.path.exists(OBS_PATH):
        return keys
    with open(OBS_PATH, encoding="utf-8") as f:
        for line in f:
            try:
                rec = json.loads(line)
                keys.add((rec.get("source"), rec.get("period")))
            except ValueError:
                continue
    return keys


def append_observations(records: List[Dict[str, Any]]) -> int:
    os.makedirs(OBS_DIR, exist_ok=True)
    existing = _existing_keys()
    observed_at = now_kst().isoformat()
    n = 0
    with open(OBS_PATH, "a", encoding="utf-8") as f:
        for rec in records:
            key = (rec.get("source"), rec.get("period"))
            if key in existing:
                continue
            rec = {"observed_at": observed_at, **rec}
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
            existing.add(key)
            n += 1
    return n


def collect(write: bool = True) -> Dict[str, Any]:
    asof = now_kst().replace(tzinfo=None)
    sess = requests.Session()
    fetchers = [
        ("aaii", lambda: fetch_aaii(sess)),
        ("naaim", lambda: fetch_naaim(sess)),
        ("finra_short", lambda: fetch_finra_short(asof, sess)),
        ("insider_form4", lambda: fetch_insider_form4(asof, sess)),
    ]
    records = []
    status = {}
    for name, fn in fetchers:
        try:
            rec = fn()
        except Exception as e:  # noqa: BLE001 — 소스 하나 실패가 전체 막지 않게
            logger.warning("%s 예외: %s", name, e)
            rec = None
        if rec:
            records.append(rec)
            status[name] = "ok"
        else:
            status[name] = "skip"
    appended = append_observations(records) if write else 0
    summary = {"status": status, "fetched": len(records), "appended": appended,
               "records": records}
    logger.info("관측 로깅: %s | append %s건", status, appended)
    return summary


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out = collect()
    print(json.dumps(out, ensure_ascii=False, indent=2))

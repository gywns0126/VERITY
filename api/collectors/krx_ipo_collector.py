"""
KRX 신규상장(IPO) 통계 collector — 막스 5번째 사이클 신호 "신규 딜 품질" 입력 source.

배경 (2026-06-07, action_queue 37407c7f):
  api/intelligence/market_horizon.py 의 classify_new_listing_quality (V2.3) 가
  portfolio["new_listings"] 6키 schema 를 소비. 데이터 source 부재 시 신호 항상 None.
  본 collector 가 그 source 를 채운다.

데이터 source = 38커뮤니케이션 (38.co.kr) 신규상장 페이지.
  · 선정 이유: 막스 신호 = "공모가 대비 첫날 수익률"(따상 현상). 공모가 + 시초가 를
    한 테이블에 동시 제공하는 유일 source. KRX 공식 data portal 은 공모가 미제공.
    [[feedback_source_attribution_discipline]] 단일 명확 출처 + 자체 산출 명시.
  · 실호출 1회 검증 완료 (2026-06-07): o=nw 페이지 9컬럼, page 당 20행 ~3개월,
    5년 = ~20페이지. 월 1회 cron 이라 트래픽 부담 0. [[feedback_real_call_over_llm_consensus]].
  · 향후 hardening 후보(검증 큐): KRX 공식 + DART 증권신고서 cross-check.

산출 = data/new_listings.json (portfolio.new_listings 6키 + 메타).
  · 첫날 수익률 정의 = 공모가 → 시초가 (시초수익률, 38 col[7]). 공식 종가 미제공 →
    시초가가 mania 강도 proxy (수요 기반 개장가). 가설, N 병기.
  · 스팩(SPAC) 제외 — 공모가 2000원 고정·기계적 첫날 변동 → return 신호 희석.

방어: HTML 형식 변경/네트워크 실패 시 graceful (기존 파일 보존, 신호 None 유지).
"""
from __future__ import annotations

import html as _html
import json
import logging
import os
import re
import statistics
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

import requests

from api.config import DATA_DIR, now_kst

logger = logging.getLogger(__name__)

BASE_URL = "http://www.38.co.kr/html/fund/index.htm"
OUT_PATH = os.path.join(DATA_DIR, "new_listings.json")

_DATE_RE = re.compile(r"^\d{4}/\d{2}/\d{2}$")
_TR_RE = re.compile(r"<tr[^>]*>(.*?)</tr>", re.S | re.I)
_TD_RE = re.compile(r"<td[^>]*>(.*?)</td>", re.S | re.I)
_TAG_RE = re.compile(r"<[^>]+>")

# 윈도 = 90일. 5년 baseline = 20 윈도.
WINDOW_DAYS = 90
BASELINE_WINDOWS = 20

# 시초가 가격제한폭 제도 변경 시행일 (KRX 2023-06-26): 공모가 90~200% → 60~400%.
# 첫날 시초수익률 상한이 +100% → +300% 로 구조적 단절. return baseline 은 동일 regime
# 내로만 비교해야 z_return 이 sentiment 를 측정(제도 artifact 배제). count 는 가격제한과
# 무관 → 5년 전체 유지. 출처: thevaluenews.co.kr/news/175426, alphabiz.co.kr/news/view/1065592919093766.
REGIME_START = datetime(2023, 6, 26)


def _clean(cell: str) -> str:
    txt = _TAG_RE.sub("", cell)
    txt = _html.unescape(txt)
    return re.sub(r"\s+", " ", txt).strip()


def _to_int(s: str) -> Optional[int]:
    s = s.replace(",", "").strip()
    if not re.match(r"^-?\d+$", s):
        return None
    return int(s)


def _to_pct(s: str) -> Optional[float]:
    s = s.replace("%", "").replace(",", "").strip()
    try:
        return float(s)
    except ValueError:
        return None


def parse_rows(page_html: str) -> List[Dict[str, Any]]:
    """38.co.kr 신규상장 페이지 HTML → 레코드 list.

    컬럼 (비어있지 않은 td 기준):
      [0] 종목명 [1] 신규상장일 [2] 현재가 [3] 전일대비% [4] 공모가
      [5] 현재수익률% [6] 시초가 [7] 시초수익률% [8] 첫날고가
    예정/미상장(시초수익률 파싱 불가) 행은 자동 제외.
    """
    out: List[Dict[str, Any]] = []
    for tr in _TR_RE.findall(page_html):
        cells = [_clean(c) for c in _TD_RE.findall(tr)]
        cells = [c for c in cells if c]  # 빈 셀만 제거 ('-'/'%' placeholder 는 유지)
        if len(cells) < 8:
            continue
        name = cells[0]
        date_s = cells[1]
        if not _DATE_RE.match(date_s):
            continue
        gongmo = _to_int(cells[4])
        first_day_pct = _to_pct(cells[7])
        if gongmo is None or first_day_pct is None:
            # 예정/미상장 또는 형식 어긋남 → skip (방어: 컬럼 shift 행도 여기서 배제)
            continue
        out.append(
            {
                "name": name,
                "listing_date": date_s.replace("/", "-"),
                "offer_price": gongmo,
                "first_day_return_pct": first_day_pct,
                "is_spac": "스팩" in name,
            }
        )
    return out


def _fetch_page(sess: requests.Session, page: int, headers: Dict[str, str], retries: int = 1) -> Optional[str]:
    """단일 페이지 HTML. 단발 throttle/hiccup 대비 1회 재시도(backoff).
    None = 영구 실패(차단/네트워크) → caller 가 truncate 로 판단."""
    for attempt in range(retries + 1):
        try:
            r = sess.get(BASE_URL, params={"o": "nw", "page": page}, headers=headers, timeout=12)
            if r.status_code == 200:
                r.encoding = "euc-kr"  # 38.co.kr = EUC-KR
                return r.text
            logger.warning("38.co.kr HTTP %s (page %s, try %s)", r.status_code, page, attempt + 1)
        except requests.RequestException as e:
            logger.warning("38.co.kr 네트워크 실패 (page %s, try %s): %s", page, attempt + 1, e)
        if attempt < retries:
            time.sleep(2.0 * (attempt + 1))
    return None


def fetch_records(max_pages: int = 30, sleep_s: float = 0.4, session: Optional[requests.Session] = None) -> Dict[str, Any]:
    """신규상장 페이지 pagination → 레코드 누적. (name, listing_date) dedupe.

    Returns {records, pages_ok, truncated, stop_reason} — truncated=True 면
    중간 차단/실패로 baseline coverage 불완전(throttle 의심). collect() 가 gate.
    """
    sess = session or requests.Session()
    headers = {"User-Agent": "Mozilla/5.0 VERITY/1.0 ipo-collector"}
    seen = set()
    records: List[Dict[str, Any]] = []
    pages_ok = 0
    truncated = False
    stop_reason = "max_pages"
    for page in range(1, max_pages + 1):
        page_html = _fetch_page(sess, page, headers)
        if page_html is None:
            # 페이지 1 실패 = 완전 차단. 그 외 = 중간 truncate (부분 데이터).
            truncated = True
            stop_reason = "blocked" if page == 1 else f"truncated_at_page_{page}"
            break
        rows = parse_rows(page_html)
        if not rows:
            stop_reason = f"empty_page_{page}"
            break
        new_in_page = 0
        for rec in rows:
            key = (rec["name"], rec["listing_date"])
            if key in seen:
                continue
            seen.add(key)
            records.append(rec)
            new_in_page += 1
        pages_ok += 1
        if new_in_page == 0:
            stop_reason = f"no_new_page_{page}"
            break
        if sleep_s:
            time.sleep(sleep_s)
    return {"records": records, "pages_ok": pages_ok, "truncated": truncated, "stop_reason": stop_reason}


def _parse_date(s: str) -> Optional[datetime]:
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return None


def aggregate(records: List[Dict[str, Any]], asof: datetime) -> Dict[str, Any]:
    """레코드 → portfolio.new_listings 6키 schema + 메타.

    · recent = 직전 90일. baseline = 그 이전 90일 윈도 × 최대 20개(5년).
    · 스팩 제외. 윈도별 count/mean(first_day_pct) 산출 → mean/sigma.
    · baseline 윈도 통계로 z 비교가 apples-to-apples (recent 도 90일 윈도).
    """
    # listing_date 는 naive(날짜만) → 비교 위해 asof 도 naive 자정으로 정규화.
    asof_d = asof.replace(hour=0, minute=0, second=0, microsecond=0, tzinfo=None)
    recent_cut = asof_d - timedelta(days=WINDOW_DAYS)

    def _ret(rec: Dict[str, Any]) -> float:
        return float(rec["first_day_return_pct"])

    deals = []
    for rec in records:
        if rec.get("is_spac"):
            continue
        d = _parse_date(rec["listing_date"])
        if d is None or d > asof_d:
            continue
        deals.append((d, _ret(rec)))

    recent = [r for (d, r) in deals if d > recent_cut]
    recent_count = len(recent)
    recent_avg = round(statistics.mean(recent), 2) if recent else None

    # 최古 관측일 — 이보다 오래된(미관측) 윈도를 count=0 으로 오인하지 않기 위함.
    # (page-cap 또는 throttle 로 pagination 이 5년 다 못 가면 빈 윈도 ≠ "IPO 0건".)
    oldest_d = min((d for (d, _r) in deals), default=asof_d)

    # baseline 윈도: (recent_cut - 90*(i+1), recent_cut - 90*i] for i in 0..N-1
    #   · count → 관측된(lo ≥ 최古일) 윈도만 (가격제한 무관, 5년 내).
    #   · return → 추가로 REGIME_START 이후 윈도만 (제도 단절 배제, apples-to-apples).
    window_counts: List[int] = []
    window_return_means: List[float] = []
    for i in range(BASELINE_WINDOWS):
        hi = recent_cut - timedelta(days=WINDOW_DAYS * i)
        lo = recent_cut - timedelta(days=WINDOW_DAYS * (i + 1))
        if lo < oldest_d:
            continue  # 부분/미관측 윈도 → 집계 제외 (false zero 방지)
        in_win = [r for (d, r) in deals if lo < d <= hi]
        window_counts.append(len(in_win))
        if in_win and lo >= REGIME_START:
            window_return_means.append(statistics.mean(in_win))

    n_data_windows = sum(1 for c in window_counts if c > 0)

    baseline_count = round(statistics.mean(window_counts), 2) if window_counts else None
    baseline_count_sigma = round(statistics.pstdev(window_counts), 2) if len(window_counts) > 1 else None
    baseline_return = round(statistics.mean(window_return_means), 2) if window_return_means else None
    baseline_return_sigma = round(statistics.pstdev(window_return_means), 2) if len(window_return_means) > 1 else None

    return {
        # ── portfolio.new_listings 6키 (market_horizon classify_new_listing_quality 입력) ──
        "recent_3m_count": recent_count,
        "recent_3m_avg_first_day_pct": recent_avg,
        "baseline_5y_count": baseline_count,
        "baseline_5y_first_day_pct": baseline_return,
        "baseline_count_sigma": baseline_count_sigma,
        "baseline_return_sigma": baseline_return_sigma,
        # ── 메타 (RULE 7 N 병기 / [[feedback_macro_timestamp_policy]]) ──
        "_meta": {
            "collected_at": asof.strftime("%Y-%m-%dT%H:%M:%S%z") or asof.isoformat(),
            "source": "38커뮤니케이션 (38.co.kr) 신규상장",
            "first_day_return_def": "공모가 → 시초가 (시초수익률). 가설, 공식 종가 미제공",
            "spac_excluded": True,
            "return_baseline_regime_start": REGIME_START.strftime("%Y-%m-%d"),
            "return_baseline_note": "시초가 제도(60~400%) 동일 regime 내 윈도만 — 제도 단절 배제",
            "n_recent_deals": recent_count,
            "n_baseline_count_windows_with_data": n_data_windows,
            "n_baseline_return_windows": len(window_return_means),
            "n_total_deals_5y": len(deals),
            "window_days": WINDOW_DAYS,
            "baseline_windows": BASELINE_WINDOWS,
        },
    }


# return baseline 이 의미를 가지려면 regime(2023-06-26) 이후 최소 윈도 필요.
# 차단/throttle 로 페이지가 과거로 못 가면 이 값들이 부족 → loud gate.
MIN_RETURN_WINDOWS = 4   # post-regime 90일 윈도 ≥ 4개 (≈ 1년)
MIN_TOTAL_DEALS = 30     # 5년 비-SPAC 딜 표본 하한


def collect(max_pages: int = 30, write: bool = True) -> Dict[str, Any]:
    asof = now_kst()
    fetched = fetch_records(max_pages=max_pages)
    records = fetched["records"]
    n = len(records)

    # 관측성: GH 로그에 항상 요약 노출 (검증 가능). [[feedback_data_collection_verification_mandatory]].
    oldest = min((r["listing_date"] for r in records), default=None)
    newest = max((r["listing_date"] for r in records), default=None)
    logger.info("fetch 요약: records=%s pages_ok=%s stop=%s 범위=%s~%s truncated=%s",
                n, fetched["pages_ok"], fetched["stop_reason"], oldest, newest, fetched["truncated"])

    # 0건 = 완전 차단(throttle/형식 변경). 기존 파일 보존, 호출자에 실패 신호.
    if n == 0:
        logger.error("신규상장 레코드 0건 (stop=%s) — 차단 의심. 기존 파일 보존, write skip",
                     fetched["stop_reason"])
        return {"_error": "no_records", "_stop_reason": fetched["stop_reason"],
                "_meta": {"collected_at": asof.isoformat()}}

    result = aggregate(records, asof)
    meta = result["_meta"]
    meta["pages_ok"] = fetched["pages_ok"]
    meta["fetch_truncated"] = fetched["truncated"]
    meta["fetch_stop_reason"] = fetched["stop_reason"]
    meta["oldest_listing"] = oldest

    # ── coverage gate: 부분 데이터(중간 차단)면 신호 신뢰 저하 → 표식 + 호출자 경고 ──
    n_ret = meta.get("n_baseline_return_windows", 0)
    warnings_list = []
    if fetched["truncated"]:
        warnings_list.append(f"fetch truncated ({fetched['stop_reason']})")
    if n < MIN_TOTAL_DEALS:
        warnings_list.append(f"deals {n} < {MIN_TOTAL_DEALS}")
    if n_ret < MIN_RETURN_WINDOWS:
        warnings_list.append(f"return windows {n_ret} < {MIN_RETURN_WINDOWS}")
    meta["coverage_ok"] = not warnings_list
    if warnings_list:
        meta["coverage_warnings"] = warnings_list
        logger.warning("coverage 경고: %s — 신호는 산출하되 예비(저신뢰)", "; ".join(warnings_list))

    if write:
        os.makedirs(DATA_DIR, exist_ok=True)
        tmp = OUT_PATH + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        os.replace(tmp, OUT_PATH)
        logger.info("new_listings.json 저장: recent=%s 첫날%%=%s baseline=%s coverage_ok=%s",
                    result.get("recent_3m_count"), result.get("recent_3m_avg_first_day_pct"),
                    result.get("baseline_5y_count"), meta["coverage_ok"])
    return result


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    out = collect()
    print(json.dumps(out, ensure_ascii=False, indent=2))
    # 0건(차단) = cron 실패로 노출 (silent green 방지, dart_batch 3주 silent 선례 회피).
    # coverage 경고는 데이터는 쓰되 exit 0 (예비 신호로 유지) — 부분이라도 None 보다 나음.
    if out.get("_error"):
        sys.exit(1)
    sys.exit(0)

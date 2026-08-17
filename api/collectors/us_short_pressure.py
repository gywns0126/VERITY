#!/usr/bin/env python3
"""
미장 공매도 압력 — 종목별. FINRA 일별 공매도 + Reg SHO 임계종목 + SEC 결제불이행(FTD).

🚨 왜 신설했나 (2026-08-17)
  경쟁 서비스(StockPulse) 실측 중 "RegSHO" 탭을 보고 우리 보유를 감사한 결과:
    · FINRA CNMSshvol 은 **이미 매일 내려받고 있었다**(us_market_observations.py).
      그런데 시장 aggregate(ΣShort/ΣTotal) 한 숫자로 접어버리고 **종목별 행을 버렸다.**
      같은 호출·같은 바이트인데 종목 축이 통째로 사라지던 것 — 수집이 아니라 폐기가 문제였다.
    · Reg SHO **임계종목 목록**(지속 결제불이행)과 SEC **FTD** 는 보유 0.
  셋을 한 파일로 모아 종목 조인에 싣는다.

세 축이 다른 것을 잰다 (섞지 말 것):
  · short_ratio  = 그날 체결 중 공매도 비중. **잔고가 아니라 거래 흐름**이다.
                   시장조성·헤지 체결이 섞여 있어 그 자체로 방향 신호가 아니다.
  · threshold    = 5거래일 연속 결제불이행 + 1만주 + 발행주식 0.5% 초과 = 규제 임계.
                   여기 오르면 T+13 강제 매수(buy-in) 대상이라 **압축 위험**이 실재한다.
  · ftd_quantity = 결제 실패 주식 수(반월 공시, 약 1개월 지연). 느리지만 유일한 실측 잔량.

⚠️ 관측 ONLY — 점수/결정 wire 0. 승격은 사전등록 통과 후 하나씩
   ([[project_observation_scoring_prereg_queue]], [[feedback_methodology_pre_registration]]).

소스 실호출 검증 완료 (2026-08-17, 4/4 HTTP 200):
  · FINRA     cdn.finra.org/equity/regsho/daily/CNMSshvol{YYYYMMDD}.txt
              Date|Symbol|ShortVolume|ShortExemptVolume|TotalVolume|Market (pipe)
  · NASDAQ    nasdaqtrader.com/dynamic/symdir/regsho/nasdaqth{YYYYMMDD}.txt
              Symbol|Security Name|Market Category|Reg SHO Threshold Flag|Rule 3210|Filler
  · NYSE      nyse.com/api/regulatory/threshold-securities/download?selectedDate=YYYY-MM-DD
              Symbol|Security Name|Market Category|Reg SHO Threshold Flag|Filler|Filler
  · SEC FTD   목록 페이지에서 cnsfails{YYYYMM}{a|b}.zip 링크를 뽑아 **날짜순 최대**를 쓴다.
              🚨 알파벳 정렬로 고르면 202004b 가 최신으로 잡힌다(같은 날 실수). 반드시
              (YYYYMM, half) 튜플로 정렬할 것.

방어: 소스별 graceful. 한 소스가 죽어도 나머지는 산다.
🚨 단 **전 소스 실패 = exit 1.** 건수 0 인데 성공 종료하면 조용한 결손이 된다
   ([[feedback_cluster_silent_defect]]).
"""
from __future__ import annotations

import io
import json
import logging
import os
import re
import sys
import urllib.request
import zipfile
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional, Tuple

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from api.config import DATA_DIR, now_kst  # noqa: E402
from api.utils import market_calendar as _mcal  # noqa: E402

logger = logging.getLogger(__name__)

OUT_PATH = os.path.join(DATA_DIR, "us_short_pressure.json")

# SEC 는 연락처 포함 UA 를 요구한다. 나머지도 봇 UA 로 막히는 곳이 있어 동일 UA 를 쓴다.
_UA = {"User-Agent": "VERITY/1.0 (gywns0126@gmail.com)"}

FINRA_TMPL = "https://cdn.finra.org/equity/regsho/daily/CNMSshvol{ymd}.txt"
NASDAQ_TH_TMPL = "https://www.nasdaqtrader.com/dynamic/symdir/regsho/nasdaqth{ymd}.txt"
NYSE_TH_TMPL = ("https://www.nyse.com/api/regulatory/threshold-securities/"
                "download?selectedDate={iso}")
SEC_FTD_INDEX = "https://www.sec.gov/data-research/sec-markets-data/fails-deliver-data"

# 거래일을 며칠까지 거슬러 볼 것인가 (당일 파일이 아직 안 올라온 경우 대비).
_LOOKBACK_SESSIONS = 5


def _get(url: str, timeout: int = 60) -> bytes:
    return urllib.request.urlopen(urllib.request.Request(url, headers=_UA), timeout=timeout).read()


def _recent_sessions(n: int = _LOOKBACK_SESSIONS) -> List[date]:
    """오늘부터 거슬러 미국 거래일 n 개 (최신순)."""
    out: List[date] = []
    d = now_kst().date()
    for _ in range(n * 4):
        if len(out) >= n:
            break
        if _mcal.is_trading_day(d, "US"):
            out.append(d)
        d -= timedelta(days=1)
    return out


# ── ① FINRA 일별 공매도 (종목별) ────────────────────────────────────────────
def fetch_finra_short_volume() -> Tuple[Dict[str, Dict[str, Any]], Optional[str]]:
    """{symbol: {short_vol, total_vol, short_ratio}}, as_of(YYYYMMDD)."""
    for d in _recent_sessions():
        ymd = d.strftime("%Y%m%d")
        try:
            raw = _get(FINRA_TMPL.format(ymd=ymd)).decode("utf-8", "ignore")
        except Exception as e:  # noqa: BLE001 — 소스별 graceful
            logger.info("FINRA %s 미가용 (%s)", ymd, type(e).__name__)
            continue
        out: Dict[str, Dict[str, Any]] = {}
        for line in raw.splitlines()[1:]:
            parts = line.split("|")
            if len(parts) < 5 or parts[0] == "Date":
                continue
            sym = parts[1].strip().upper()
            try:
                sv, tv = float(parts[2]), float(parts[4])
            except ValueError:
                continue
            if not sym or tv <= 0:
                continue
            # short_vol 은 싣지 않는다 — short_ratio × total_vol 로 복원되고, 15k 종목이면
            # 그 한 필드가 파일의 17% 다. total_vol 은 유동성 맥락이라 남긴다.
            out[sym] = {
                "total_vol": round(tv),
                "short_ratio": round(sv / tv * 100, 2),
            }
        if out:
            logger.info("FINRA %s — %d 종목", ymd, len(out))
            return out, ymd
    return {}, None


# ── ② Reg SHO 임계종목 (NASDAQ + NYSE 합집합) ───────────────────────────────
def _parse_threshold(text: str) -> Dict[str, str]:
    """pipe 목록 → {symbol: security_name}. 두 거래소가 같은 헤더 형태를 쓴다."""
    out: Dict[str, str] = {}
    for line in text.splitlines()[1:]:
        parts = line.split("|")
        if len(parts) < 4:
            continue
        sym = parts[0].strip().upper()
        # Reg SHO Threshold Flag 열이 'Y' 인 행만. 헤더 순서는 두 소스 동일(4번째).
        if not sym or parts[3].strip().upper() != "Y":
            continue
        out[sym] = parts[1].strip()
    return out


def fetch_threshold_lists() -> Tuple[Dict[str, Dict[str, Any]], Optional[str], List[str]]:
    """{symbol: {name, venues[]}}, as_of(YYYYMMDD), 실패한 거래소 목록."""
    for d in _recent_sessions():
        ymd, iso = d.strftime("%Y%m%d"), d.isoformat()
        merged: Dict[str, Dict[str, Any]] = {}
        failed: List[str] = []
        for venue, url in (("NASDAQ", NASDAQ_TH_TMPL.format(ymd=ymd)),
                           ("NYSE", NYSE_TH_TMPL.format(iso=iso))):
            try:
                got = _parse_threshold(_get(url).decode("utf-8", "ignore"))
            except Exception as e:  # noqa: BLE001
                failed.append(venue)
                logger.info("%s threshold %s 미가용 (%s)", venue, ymd, type(e).__name__)
                continue
            for sym, name in got.items():
                row = merged.setdefault(sym, {"name": name, "venues": []})
                row["venues"].append(venue)
        if merged:
            logger.info("Threshold %s — %d 종목 (실패 %s)", ymd, len(merged), failed or "없음")
            return merged, ymd, failed
    return {}, None, ["NASDAQ", "NYSE"]


# ── ③ SEC 결제불이행 (FTD) — 반월 ───────────────────────────────────────────
def fetch_sec_ftd() -> Tuple[Dict[str, Dict[str, Any]], Optional[str]]:
    """{symbol: {ftd_qty_max, ftd_days}}, 기간 라벨(YYYYMM{a|b}).

    반월 파일 안에 결제일이 여러 개 있다. 종목별로 **최대 실패 수량**과 등장 일수를 남긴다
    (합계는 같은 잔량을 며칠 중복 계상하므로 쓰지 않는다).
    """
    try:
        html = _get(SEC_FTD_INDEX, timeout=40).decode("utf-8", "ignore")
    except Exception as e:  # noqa: BLE001
        logger.info("SEC FTD 목록 미가용 (%s)", type(e).__name__)
        return {}, None
    links = set(re.findall(r'href="([^"]*cnsfails(\d{6})([ab])\.zip)"', html))
    if not links:
        return {}, None
    # 🚨 알파벳 정렬 금지 — (YYYYMM, half) 로 정렬해야 진짜 최신이 나온다.
    href, ym, half = max(((h, y, s) for h, y, s in links), key=lambda r: (r[1], r[2]))
    url = href if href.startswith("http") else "https://www.sec.gov" + href
    try:
        z = zipfile.ZipFile(io.BytesIO(_get(url, timeout=120)))
        text = z.read(z.namelist()[0]).decode("utf-8", "ignore")
    except Exception as e:  # noqa: BLE001
        logger.info("SEC FTD 파일 미가용 (%s)", type(e).__name__)
        return {}, None
    out: Dict[str, Dict[str, Any]] = {}
    for line in text.splitlines()[1:]:
        parts = line.split("|")
        if len(parts) < 4:
            continue
        sym = parts[2].strip().upper()
        try:
            qty = int(parts[3])
        except ValueError:
            continue
        if not sym:
            continue
        row = out.setdefault(sym, {"ftd_qty_max": 0, "ftd_days": 0})
        row["ftd_qty_max"] = max(row["ftd_qty_max"], qty)
        row["ftd_days"] += 1
    logger.info("SEC FTD %s%s — %d 종목", ym, half, len(out))
    return out, f"{ym}{half}"


def collect() -> Dict[str, Any]:
    short_vol, sv_asof = fetch_finra_short_volume()
    thresh, th_asof, th_failed = fetch_threshold_lists()
    ftd, ftd_period = fetch_sec_ftd()

    symbols = set(short_vol) | set(thresh) | set(ftd)
    out_map: Dict[str, Dict[str, Any]] = {}
    for sym in symbols:
        row: Dict[str, Any] = {}
        row.update(short_vol.get(sym, {}))
        if sym in thresh:
            row["threshold"] = True
            row["threshold_venues"] = thresh[sym]["venues"]
            if thresh[sym].get("name"):
                row["name"] = thresh[sym]["name"]
        row.update(ftd.get(sym, {}))
        # 🚨 저유동 노이즈 제외 — 단 **신호를 든 종목은 거래량과 무관하게 남긴다.**
        #   임계종목·FTD 는 소형·워런트에 몰려 있어서 거래량으로만 자르면 정작 볼 것이 잘린다.
        #   현 컷(5,000주)에서 제외되는 종목 중 신호 보유 = 0 건으로 실측 확인(2026-08-17).
        if not row.get("threshold") and not row.get("ftd_qty_max") \
                and (row.get("total_vol") or 0) < 5000:
            continue
        out_map[sym] = row

    return {
        "_meta": {
            "generated_at": now_kst().isoformat(timespec="seconds"),
            "short_volume_as_of": sv_asof,
            "threshold_as_of": th_asof,
            "threshold_venues_failed": th_failed,
            "ftd_period": ftd_period,
            "counts": {
                "symbols": len(out_map),
                "short_volume": len(short_vol),
                "threshold": len(thresh),
                "ftd": len(ftd),
            },
            "source": ("FINRA CNMSshvol(일별 공매도 체결) · "
                       "NASDAQ/NYSE Reg SHO threshold list · SEC cnsfails(FTD, 반월)"),
            "basis": ("short_ratio = 당일 공매도 체결 ÷ 총 체결(%). 잔고가 아니다 — "
                      "시장조성·헤지 체결 포함. threshold = 5거래일 연속 결제불이행 규제 임계 "
                      "(T+13 강제 매수 대상). ftd_qty_max = 반월 내 최대 결제 실패 주식 수 "
                      "(약 1개월 지연). 관측 전용 · 점수 미반영."),
        },
        "map": out_map,
    }


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    payload = collect()
    counts = payload["_meta"]["counts"]
    # 🚨 전 소스 실패 = 실패로 끝낸다. 빈 파일을 성공으로 덮으면 조용한 결손이 된다.
    if counts["symbols"] == 0:
        logger.error("[us_short_pressure] 전 소스 실패 — 기존 파일 유지하고 종료")
        return 1
    os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, separators=(",", ":"))
    m = payload["_meta"]
    logger.info(
        "[us_short_pressure] %d 종목 · 공매도 %d(%s) · 임계 %d(%s) · FTD %d(%s) → %s",
        counts["symbols"], counts["short_volume"], m["short_volume_as_of"],
        counts["threshold"], m["threshold_as_of"], counts["ftd"], m["ftd_period"], OUT_PATH,
    )
    if m["threshold_venues_failed"]:
        logger.warning("[us_short_pressure] 임계 목록 일부 소스 실패: %s",
                       m["threshold_venues_failed"])
    return 0


if __name__ == "__main__":
    sys.exit(main())

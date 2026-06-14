"""
ff3_factors.py — Fama-French 3-factor 주간 시계열 fetch + 파싱 (Kenneth French Data Library, 무료).

2026-06-14 신설. CoMOM(comomentum, Lou-Polk 2022) residual 산출용 — 종목 주간수익률을
FF3(Mkt-RF/SMB/HML)로 잔차화하기 위함. 공개 무료 데이터(저작권 제약 없음, 학술 표준).

소스: https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/
  F-F_Research_Data_Factors_weekly_CSV.zip (Friday-dated 주간, 1926~, 단위 = %).
"""
from __future__ import annotations

import io
import logging
import os
import zipfile
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)

FF3_WEEKLY_URL = (
    "https://mba.tuck.dartmouth.edu/pages/faculty/ken.french/ftp/"
    "F-F_Research_Data_Factors_weekly_CSV.zip"
)
_UA = "Mozilla/5.0 (VERITY academic-grounding/CoMOM)"


def _parse_ff3_csv(text: str) -> pd.DataFrame:
    """FF3 CSV 텍스트 → DataFrame[date, mkt_rf, smb, hml, rf] (소수, % → /100).

    헤더 블록(설명문) skip → `,Mkt-RF,SMB,HML,RF` 이후 8자리 날짜 행만 파싱.
    주간 섹션 끝(빈 줄/비-날짜) 에서 중단 (annual 섹션 append 방어).
    """
    rows = []
    started = False
    for line in text.splitlines():
        s = line.strip()
        if not started:
            if s.replace(" ", "").startswith(",Mkt-RF,SMB,HML,RF"):
                started = True
            continue
        parts = [p.strip() for p in s.split(",")]
        if len(parts) < 5 or not (parts[0].isdigit() and len(parts[0]) == 8):
            break  # 주간 데이터 섹션 종료
        try:
            d = pd.to_datetime(parts[0], format="%Y%m%d")
            rows.append((d, float(parts[1]) / 100.0, float(parts[2]) / 100.0,
                         float(parts[3]) / 100.0, float(parts[4]) / 100.0))
        except (ValueError, TypeError):
            continue
    if not rows:
        raise ValueError("FF3 CSV 파싱 0행 — 포맷 변경 의심")
    df = pd.DataFrame(rows, columns=["date", "mkt_rf", "smb", "hml", "rf"]).set_index("date")
    return df


def fetch_ff3_weekly(
    cache_path: Optional[str] = None, max_age_days: int = 7,
    session: Optional[requests.Session] = None,
) -> pd.DataFrame:
    """FF3 주간 fetch (cache_path 있으면 parquet 캐시, max_age_days 초과 시 갱신)."""
    if cache_path and os.path.exists(cache_path):
        try:
            import time
            age_d = (time.time() - os.path.getmtime(cache_path)) / 86400.0
            if age_d <= max_age_days:
                return pd.read_parquet(cache_path)
        except Exception as e:  # noqa: BLE001 — 캐시 손상 시 재fetch
            logger.warning("FF3 캐시 읽기 실패, 재fetch: %s", e)

    sess = session or requests.Session()
    r = sess.get(FF3_WEEKLY_URL, headers={"User-Agent": _UA}, timeout=30)
    r.raise_for_status()
    z = zipfile.ZipFile(io.BytesIO(r.content))
    text = z.read(z.namelist()[0]).decode("latin-1")
    df = _parse_ff3_csv(text)

    if cache_path:
        try:
            os.makedirs(os.path.dirname(cache_path), exist_ok=True)
            df.to_parquet(cache_path)
        except Exception as e:  # noqa: BLE001
            logger.warning("FF3 캐시 저장 실패(무시): %s", e)
    return df

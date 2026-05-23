"""ecos_fx_daily — 한국은행 ECOS 일별 USD/KRW 시계열 + σ 검증 collector.

배경 (2026-05-23, A2 PM 사전등록 후속):
  [[project_after_tax_sharpe_kr_us]] / [[conviction_selector.py]] 의 σ_FX 가정 0.08
  (DEFAULT_SIGMA_FX) 시점 검증 의제. Perplexity A2 자문
  ([[2026-05-23_Track1_BCE_자문_3건.md]]) = 2026-05 시점 σ_FX 0.08 "다소 보수적"
  평가. 실측 검증 cron 박음 = ECOS 일별 USD/KRW 시계열 → 30/60/90d 실현 σ 산출.

산식:
  σ_Nd = stdev(log(R_t / R_{t-1}) for t in [now-N, now]) × √252

ECOS API:
  통계코드 731Y001 (주요국 통화의 대원화 환율, D 일별)
  항목코드 0000001 (미국달러 USD)
  URL: /StatisticSearch/{KEY}/json/kr/{idx_start}/{idx_end}/731Y001/D/{YYYYMMDD}/{YYYYMMDD}/0000001

적재:
  data/macro/usd_krw_daily.jsonl — 1줄 = 1일 entry {date, value, fetched_at}
  rolling = 직전 252 영업일 (1년) 유지 충분
  σ 산출 = compute_realized_sigma(history, days) → annualized

운영:
  silent skip 차단 ([[feedback_data_collection_verification_mandatory]]):
    fetch 실패 / parse 실패 / 0 row 모두 stderr 명시 + return None.

ρ_S_FX (KOSPI/SP500 vs USD/KRW 자산별 상관) = 별 sprint 큐 — KOSPI/SP500
시계열 fetch + 12m rolling 상관 산출.
"""
from __future__ import annotations

import json
import math
import os
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from api.config import ECOS_API_KEY, DATA_DIR, now_kst

_LOG_PATH = Path(DATA_DIR) / "macro" / "usd_krw_daily.jsonl"

# ECOS 통계코드 / 항목코드
_STATS_CODE = "731Y001"        # 주요국 통화의 대원화 환율 (D)
_ITEM_CODE_USD = "0000001"     # 미국달러
_CYCLE = "D"

# 산식 상수
_TRADING_DAYS_PER_YEAR = 252


def _ymd(dt: datetime) -> str:
    return dt.strftime("%Y%m%d")


def fetch_ecos_usd_krw_daily(
    lookback_days: int = 120,
    timeout: float = 8.0,
) -> Optional[List[Dict[str, Any]]]:
    """ECOS 일별 USD/KRW 시계열 fetch.

    Args:
        lookback_days: 직전 N일 (default 120 = σ_90d 산출 + buffer)

    Returns:
        list of {date: "YYYY-MM-DD", value: float} (오름차순) 또는 None (실패).
    """
    if not ECOS_API_KEY:
        sys.stderr.write("[ecos_fx_daily] ECOS_API_KEY 미설정 — fetch 스킵\n")
        return None

    end_dt = now_kst()
    bgn_dt = end_dt - timedelta(days=lookback_days)
    # ECOS 의 인덱스 = 1-base, 한 query 최대 row 수 = 1000 (충분)
    k = quote(str(ECOS_API_KEY).strip(), safe="")
    url = (
        f"https://ecos.bok.or.kr/api/StatisticSearch/{k}/json/kr/1/1000/"
        f"{_STATS_CODE}/{_CYCLE}/{_ymd(bgn_dt)}/{_ymd(end_dt)}/{_ITEM_CODE_USD}"
    )

    try:
        resp = requests.get(url, timeout=timeout)
        resp.raise_for_status()
        payload = resp.json()
    except Exception as e:
        sys.stderr.write(f"[ecos_fx_daily] fetch 실패: {type(e).__name__}: {e}\n")
        return None

    container = payload.get("StatisticSearch") or {}
    rows = container.get("row") or []
    if not rows:
        # ECOS 에러 응답 schema 도 체크
        result = payload.get("RESULT") or {}
        if result:
            sys.stderr.write(
                f"[ecos_fx_daily] 0 row — ECOS RESULT: {result.get('CODE')} {result.get('MESSAGE')}\n"
            )
        else:
            sys.stderr.write("[ecos_fx_daily] 0 row — 응답 비정상\n")
        return None

    out: List[Dict[str, Any]] = []
    for r in rows:
        time_raw = (r or {}).get("TIME") or ""
        value_raw = (r or {}).get("DATA_VALUE") or ""
        if len(time_raw) != 8:
            continue
        try:
            value = float(value_raw)
        except (TypeError, ValueError):
            continue
        out.append({
            "date": f"{time_raw[:4]}-{time_raw[4:6]}-{time_raw[6:8]}",
            "value": value,
        })

    out.sort(key=lambda x: x["date"])
    return out


def compute_realized_sigma(
    history: List[Dict[str, Any]],
    days: int,
) -> Optional[float]:
    """직전 N영업일 로그수익률 → annualized 표준편차.

    Args:
        history: fetch_ecos_usd_krw_daily 결과 (오름차순)
        days: σ 산출 window (30/60/90)

    Returns:
        annualized σ (float) 또는 None (sample 부족).
    """
    if not history or len(history) < days + 1:
        return None

    tail = history[-(days + 1):]
    log_returns: List[float] = []
    prev = None
    for entry in tail:
        v = entry.get("value")
        if not isinstance(v, (int, float)) or v <= 0:
            continue
        if prev is not None and prev > 0:
            try:
                log_returns.append(math.log(v / prev))
            except (ValueError, ZeroDivisionError):
                pass
        prev = v

    if len(log_returns) < days // 2:  # 결측 너무 많으면 거부
        return None

    n = len(log_returns)
    mean = sum(log_returns) / n
    var = sum((r - mean) ** 2 for r in log_returns) / max(n - 1, 1)
    daily_sigma = math.sqrt(var)
    return daily_sigma * math.sqrt(_TRADING_DAYS_PER_YEAR)


def persist_history(history: List[Dict[str, Any]]) -> None:
    """data/macro/usd_krw_daily.jsonl 적재 (full overwrite, 직전 252일 유지)."""
    _LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
    tail = history[-_TRADING_DAYS_PER_YEAR:] if len(history) > _TRADING_DAYS_PER_YEAR else history
    fetched_at = now_kst().isoformat(timespec="seconds")
    with _LOG_PATH.open("w", encoding="utf-8") as f:
        for entry in tail:
            f.write(json.dumps({**entry, "fetched_at": fetched_at}, ensure_ascii=False) + "\n")


def load_persisted_history() -> List[Dict[str, Any]]:
    """data/macro/usd_krw_daily.jsonl read."""
    if not _LOG_PATH.exists():
        return []
    out: List[Dict[str, Any]] = []
    with _LOG_PATH.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return out


def run_fx_sigma_check() -> Dict[str, Any]:
    """fetch + persist + σ_30/60/90 산출 통합 cron 엔트리.

    Returns:
        {
          "fetched": bool,
          "history_count": int,
          "sigma_30d": float | None,
          "sigma_60d": float | None,
          "sigma_90d": float | None,
          "latest_date": str | None,
          "latest_value": float | None,
          "fetched_at": str,
        }
    """
    history = fetch_ecos_usd_krw_daily(lookback_days=120)
    fetched_at = now_kst().isoformat(timespec="seconds")
    result: Dict[str, Any] = {
        "fetched": False,
        "history_count": 0,
        "sigma_30d": None,
        "sigma_60d": None,
        "sigma_90d": None,
        "latest_date": None,
        "latest_value": None,
        "fetched_at": fetched_at,
    }
    if history is None:
        sys.stderr.write("[ecos_fx_daily] fetch returned None — skip persist\n")
        return result

    persist_history(history)
    result["fetched"] = True
    result["history_count"] = len(history)
    if history:
        last = history[-1]
        result["latest_date"] = last.get("date")
        result["latest_value"] = last.get("value")
    for n in (30, 60, 90):
        sigma = compute_realized_sigma(history, n)
        if sigma is not None:
            result[f"sigma_{n}d"] = round(sigma, 4)

    sys.stderr.write(
        f"[ecos_fx_daily] OK rows={len(history)} latest={result['latest_value']}@{result['latest_date']} "
        f"σ30={result['sigma_30d']} σ60={result['sigma_60d']} σ90={result['sigma_90d']} logged=True\n"
    )
    return result


if __name__ == "__main__":
    print(json.dumps(run_fx_sigma_check(), ensure_ascii=False, indent=2))

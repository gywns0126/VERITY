"""
유니버스 빌더 — Phase 2-A (2026-05-01)

KR: KRX OpenAPI K1 (krx_stk_ksq_rows_sorted_by_trading_value) 1콜로
    KOSPI+KOSDAQ 전체 + MKTCAP/ACC_TRDVAL/OHLC/LIST_SHRS 즉시 확보.
US: 정적 캐시 (data/cache/universe_us.json, 주 1회 별도 갱신)
    + 코어 화이트리스트 union 보장.

코어 화이트리스트 85종목은 항상 포함 (is_core=True).
target_size 는 ramp-up 단계별 (500/1500/3000/5000).

운영 코드 미터치 — 본 모듈은 main.py 가 호출만.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

# 코어 화이트리스트 — Phase 2-A 도 항상 포함
_CORE_KR: tuple[str, ...] = ()  # stock_data.py 의 KOSPI_MAJOR + KOSDAQ_MAJOR
_CORE_US: tuple[str, ...] = ()  # stock_data.py 의 US_MAJOR


def _load_core_pools() -> tuple[set[str], set[str]]:
    """stock_data.py 의 코어 화이트리스트를 동적 import (단일 진실)."""
    from api.collectors.stock_data import KOSPI_MAJOR, KOSDAQ_MAJOR, US_MAJOR
    kr_core = set()
    for ticker_yf in list(KOSPI_MAJOR) + list(KOSDAQ_MAJOR):
        # ticker_yf = "005930.KS" → "005930"
        digits = "".join(c for c in ticker_yf.split(".")[0] if c.isdigit())
        if len(digits) >= 6:
            kr_core.add(digits[-6:].zfill(6))
    us_core = set(t for t in US_MAJOR)
    return kr_core, us_core


def _to_int(raw: object, default: int = 0) -> int:
    if raw is None:
        return default
    s = str(raw).strip().replace(",", "")
    if not s:
        return default
    try:
        return int(float(s))
    except (ValueError, TypeError):
        return default


def _row_to_universe_entry(row: dict, kr_core: set[str], market_inferred: str) -> Optional[dict]:
    """KRX OpenAPI 행을 universe entry 로 정규화."""
    code_raw = str(row.get("ISU_CD") or row.get("ISU_SRT_CD") or "")
    digits = "".join(ch for ch in code_raw if ch.isdigit())
    if len(digits) < 6:
        return None
    ticker = digits[-6:].zfill(6)

    name = str(row.get("ISU_NM") or "")
    market = str(row.get("MKT_NM") or market_inferred or "")
    sect_tp = str(row.get("SECT_TP_NM") or "")  # "관리종목" 등이 들어올 수 있음
    market_cap = _to_int(row.get("MKTCAP"))
    trading_value = _to_int(row.get("ACC_TRDVAL"))

    # 관리종목/투자경고/거래정지 — KRX 가 SECT_TP_NM 에 표기
    sect_lower = sect_tp.lower()
    is_managed = any(kw in sect_tp for kw in ("관리", "투자경고", "투자위험", "투자주의"))
    is_suspended = "거래정지" in sect_tp or trading_value == 0  # ACC_TRDVAL=0 도 정지 의심

    return {
        "ticker": ticker,
        "name": name,
        "market": market,  # "KOSPI" or "KOSDAQ"
        "currency": "KRW",
        "market_cap": market_cap,  # 원
        "avg_trading_value_30d": trading_value,  # KRX 일별 — 30일 평균은 별도 계산 필요, 일단 일별값 보유
        "sect_tp": sect_tp,
        "is_core": ticker in kr_core,
        "is_managed": is_managed,
        "is_suspended": is_suspended,
        "tier": "core" if ticker in kr_core else "extended",
        "source": "KRX_OPENAPI_K1",
    }


def build_kr_universe(target_size: int) -> tuple[str, list[dict]]:
    """KRX OpenAPI 1콜로 KR universe 빌드. (bas_dd, entries) 반환.

    target_size 는 *시총 상위* 추출 기준. 코어 종목은 별도 union 후 dedupe.
    KRX OpenAPI 응답이 거래대금 정렬이라 시총 정렬 변환 필요.
    """
    from api.collectors.krx_openapi import krx_stk_ksq_rows_sorted_by_trading_value

    bas_dd, rows = krx_stk_ksq_rows_sorted_by_trading_value()
    if not bas_dd or not rows:
        raise RuntimeError("KRX OpenAPI K1 빈 응답 (KRX_API_KEY 또는 휴장일 누적)")

    kr_core, _ = _load_core_pools()
    entries = [e for e in (_row_to_universe_entry(r, kr_core, "") for r in rows) if e]

    # 시총 내림차순 정렬 (krx_openapi 는 거래대금 정렬이라 재정렬)
    entries.sort(key=lambda e: e["market_cap"], reverse=True)

    # 시총 상위 target_size + 코어 union (코어 종목은 시총 cut 통과 못해도 포함)
    top_n = entries[:target_size]
    top_tickers = {e["ticker"] for e in top_n}
    core_to_add = [e for e in entries if e["is_core"] and e["ticker"] not in top_tickers]
    final = top_n + core_to_add
    return bas_dd, final


def _load_us_static_cache(cache_path: Optional[Path] = None) -> list[dict]:
    """US universe 정적 캐시 로드. 캐시 부재 시 코어 + S&P 100 fallback 반환.

    실제 운영에서는 별도 weekly refresh 스크립트가 cache_path 갱신.
    """
    if cache_path is None:
        cache_path = Path("data/cache/universe_us.json")
    if cache_path.exists():
        try:
            data = json.loads(cache_path.read_text())
            if isinstance(data, list) and data:
                return data
        except Exception:
            pass

    # Fallback — 캐시 부재 시 코어 화이트리스트만 반환.
    # 운영 시 별도 weekly refresh 스크립트가 cache_path 갱신해야 함.
    # (Phase 2-A 배포 전 docs/cache_refresh_us_universe.md 참조 — 미작성)
    _, us_core = _load_core_pools()
    seen, out = set(), []
    for t in list(us_core):
        if t in seen:
            continue
        seen.add(t)
        out.append({
            "ticker": t,
            "name": t,
            "market": "US",
            "currency": "USD",
            "market_cap": 0,  # 정적 캐시 미정 — fetch 단계에서 보강
            "avg_trading_value_30d": 0,
            "is_core": t in us_core,
            "is_managed": False,
            "is_suspended": False,
            "tier": "core" if t in us_core else "extended",
            "source": "static_fallback",
        })
    return out


def build_us_universe(target_size: int, cache_path: Optional[Path] = None) -> list[dict]:
    """US universe — 정적 캐시 또는 fallback."""
    pool = _load_us_static_cache(cache_path)
    # 코어 항상 포함 + 상위 N
    cores = [e for e in pool if e["is_core"]]
    extended = [e for e in pool if not e["is_core"]]
    return cores + extended[: max(0, target_size - len(cores))]


def build_extended_universe(
    market: str,  # "KR" or "US"
    target_size: int,
    apply_hard_floor: bool = True,
) -> list[dict]:
    """Phase 2-A 메인 진입점.

    Returns:
        [
            {ticker, name, market, currency, market_cap, avg_trading_value_30d,
             is_core, is_managed, is_suspended, passes_hard_floor, added_at, tier},
            ...
        ]
    """
    market = market.upper()
    if market not in ("KR", "US"):
        raise ValueError(f"market must be 'KR' or 'US', got {market!r}")

    if market == "KR":
        bas_dd, entries = build_kr_universe(target_size)
    else:
        entries = build_us_universe(target_size)
        bas_dd = datetime.now(ZoneInfo("Asia/Seoul")).strftime("%Y%m%d")

    now_iso = datetime.now(ZoneInfo("Asia/Seoul")).isoformat()
    for e in entries:
        e["added_at"] = now_iso
        e["bas_dd"] = bas_dd

    if apply_hard_floor:
        from api.analyzers.hard_floor import apply_hard_floor as _apply
        entries = [_apply(e) for e in entries]
        # passes_hard_floor 이 False 이고 코어 아니면 제외
        entries = [
            e for e in entries
            if e.get("hard_floor_metadata", {}).get("passes", True) or e.get("is_core")
        ]
        for e in entries:
            e["passes_hard_floor"] = e.get("hard_floor_metadata", {}).get("passes", True)
    else:
        for e in entries:
            e["passes_hard_floor"] = True

    return entries

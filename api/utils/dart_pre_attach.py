"""dart_pre_attach — universe_scan stocks dict 에 DART 펀더멘털 주입.

배경 (2026-05-10):
  dart_batch_builder 가 주 1회 KR universe ~2,000 종목 DART fetch → data/dart_fundamentals_kr.json.
  universe_scan_builder 가 stock_filter 호출 시 stock dict 에 attach → wide_scan 의 5,000
  raw 단계에서 F-Score / Magic Formula 가 DART 정확값 사용.

  메모리 결정 2 정합 — KR fundamentals 1순위 = DART, 2순위 = yfinance fallback.
  결정 7 정합 — DART 주 1회 갱신 (분기 의존).

stale 처리:
  - max_stale_days = 8 (1주 + 1일 마진). 그 이상이면 cache miss → yfinance 만 사용.
  - silent skip 절대 금지 (memory feedback_data_collection_verification_mandatory).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, List, Optional

KST = timezone(timedelta(hours=9))

DART_KR_PATH = Path(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))) / "data" / "dart_fundamentals_kr.json"


def load_dart_fundamentals_kr(
    *, max_stale_days: int = 8, path: Optional[Path] = None
) -> Optional[Dict[str, Dict]]:
    """DART batch snapshot 로드. stale 시 None.

    Returns:
        {ticker_6digit: {per, pbr, roe, debt_ratio, op_margin, source, ...}} 또는 None.
    """
    p = path or DART_KR_PATH
    if not p.exists():
        print("[dart_pre_attach] cache miss — file 미존재", file=sys.stderr, flush=True)
        return None
    try:
        snap = json.loads(p.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"[dart_pre_attach] FAIL parse: {type(e).__name__}: {e}", file=sys.stderr, flush=True)
        return None

    collected = snap.get("collected_at")
    if not collected:
        print("[dart_pre_attach] cache miss — collected_at 미존재", file=sys.stderr, flush=True)
        return None

    try:
        ts = datetime.fromisoformat(collected)
    except ValueError:
        print(f"[dart_pre_attach] FAIL ts parse: {collected}", file=sys.stderr, flush=True)
        return None

    age = datetime.now(KST) - ts
    if age > timedelta(days=max_stale_days):
        print(
            f"[dart_pre_attach] stale ({age.days}일 > {max_stale_days}일) — cache 무시",
            file=sys.stderr, flush=True,
        )
        return None

    fundamentals = snap.get("fundamentals") or {}
    print(
        f"[dart_pre_attach] cache hit at={collected} fundamentals={len(fundamentals)} age={age.days}일",
        file=sys.stderr, flush=True,
    )
    return fundamentals


def attach_dart_to_stocks(
    stocks: List[dict], *, max_stale_days: int = 8, path: Optional[Path] = None
) -> dict:
    """KR 종목 stock dict 에 DART 펀더멘털 주입 (in-place).

    Args:
        stocks: get_all_stock_data 결과
        max_stale_days: cache stale 임계값

    Returns:
        {
          "attached_n": int,         # DART 데이터 attach 한 종목 수
          "kr_total_n": int,         # KR 종목 총 수
          "cache_hit": bool,         # snapshot load 성공 여부
        }

    DART 우선 정책 (메모리 결정 2):
      stock 의 per / pbr / roe / debt_ratio / op_margin 이 None / 0 일 때만 DART 값으로 보강.
      yfinance 가 정확히 채워져 있으면 (가격 의존 — per 매일 갱신) 그대로 유지.
      DART 만 있는 필드 (예: 분기 보고일 report_date) 는 항상 attach.
    """
    fundamentals = load_dart_fundamentals_kr(max_stale_days=max_stale_days, path=path)
    if not fundamentals:
        return {"attached_n": 0, "kr_total_n": 0, "cache_hit": False}

    attached = 0
    kr_total = 0
    for s in stocks:
        if (s.get("currency") or "").upper() == "USD":
            continue
        kr_total += 1
        ticker = str(s.get("ticker") or "").zfill(6)
        if not ticker or ticker not in fundamentals:
            continue
        d = fundamentals[ticker]
        # boost weak yfinance fields with DART (DART 1순위)
        if d.get("per") is not None and not s.get("per"):
            s["per"] = d["per"]
        if d.get("pbr") is not None and not s.get("pbr"):
            s["pbr"] = d["pbr"]
        if d.get("roe") is not None and (not s.get("roe") or s.get("roe") == 0):
            s["roe"] = d["roe"]
        if d.get("debt_ratio") is not None and (not s.get("debt_ratio") or s.get("debt_ratio") == 0):
            s["debt_ratio"] = d["debt_ratio"]
        if d.get("op_margin") is not None and (not s.get("operating_margin") or s.get("operating_margin") == 0):
            s["operating_margin"] = d["op_margin"]
        # DART-only 필드는 항상 attach (yfinance 미커버) — Altman X1/X2 + F-Score 9/9 활성
        # (2026-05-20 sprint, fnlttSinglAcntAll CFS 우선 + 매출원가/CF 3종 추가)
        for field in ("roa", "current_ratio", "asset_turnover", "gross_margin",
                      "working_capital", "retained_earnings", "total_assets",
                      "current_assets", "current_liabilities", "operating_profit",
                      "revenue", "cogs", "gross_profit", "net_income",
                      "operating_cashflow", "investing_cashflow",
                      "financing_cashflow", "free_cashflow"):
            v = d.get(field)
            if v is not None and (s.get(field) in (None, 0)):
                s[field] = v
        if d.get("report_date"):
            s["dart_report_date"] = d["report_date"]
        if d.get("fs_div"):
            s["dart_fs_div"] = d["fs_div"]
        s["dart_source"] = d.get("source", "unknown")
        attached += 1

    print(
        f"[dart_pre_attach] attached={attached}/{kr_total} (KR only)",
        file=sys.stderr, flush=True,
    )
    return {"attached_n": attached, "kr_total_n": kr_total, "cache_hit": True}

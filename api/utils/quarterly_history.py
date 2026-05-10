"""quarterly_history — universe 5,000 raw 펀더멘털 시계열 누적.

배경 (2026-05-10):
  yfinance 단일 스냅샷 한계 극복. 매 universe_scan run 마다 5,000 종목 핵심 펀더멘털을
  분기 jsonl 에 적재. 13주 누적 후 텐버거 leading 정량 계산 가능:
  - F-Score Δ 항목 (c3, c5, c6, c8, c9 — 4개)
  - CANSLIM C (분기 EPS 3연속 가속)
  - Magic Formula 한국개선 GP/A 가속 (KAIS 2023)
  - Buffett owner earnings (FCF margin trend)
  - ROIC 가속 (Greenblatt 표준)

저장 위치: data/stock_history/YYYY-Qn.jsonl (분기별 1 파일)
스키마: ts / ticker / market / 펀더멘털 핵심 14개 필드 (가벼운 snapshot)
        sparkline / trends 같은 무거운 필드는 제외 (storage 비용 통제)

추가 API 호출 0 — get_all_stock_data 결과를 그대로 적재.
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import List, Optional

KST = timezone(timedelta(hours=9))

# 분기 history 적재 핵심 필드 — sparkline/trends 같은 큰 필드 제외 (storage 통제)
_SNAPSHOT_FIELDS = (
    "ticker", "market", "currency", "company_type",
    "price", "market_cap",
    "per", "pbr", "eps", "roe", "roa", "div_yield",
    "debt_ratio", "current_ratio",
    "operating_margin", "profit_margin", "gross_margins",
    "revenue_growth", "eps_quarterly_growth",
    "free_cashflow", "operating_cashflow",
    "shares_outstanding", "held_pct_insiders", "held_pct_institutions",
)


def _quarter_filename(dt: datetime) -> str:
    """datetime → 'YYYY-Qn' (Q1=1~3월, Q2=4~6월, Q3=7~9월, Q4=10~12월)."""
    q = (dt.month - 1) // 3 + 1
    return f"{dt.year}-Q{q}"


def _output_path(dt: datetime, root: Optional[Path] = None) -> Path:
    base = root if root is not None else Path("data/stock_history")
    return base / f"{_quarter_filename(dt)}.jsonl"


def append_universe_snapshot(
    stocks: List[dict],
    *,
    run_at_iso: Optional[str] = None,
    output_root: Optional[Path] = None,
) -> dict:
    """5,000 raw 종목 snapshot 을 분기 jsonl 에 1줄/종목 append.

    Args:
        stocks: get_all_stock_data 결과
        run_at_iso: 명시적 timestamp (테스트용). None 이면 KST 현재.
        output_root: 출력 루트 디렉토리 (테스트용). None 이면 data/stock_history.

    Returns:
        {
          "logged": bool,            # 적재 성공 여부
          "appended_n": int,         # append 한 라인 수
          "skipped_n": int,          # ticker 결손으로 skip 한 라인 수
          "path": str,               # 적재된 파일 경로
        }

    silent 실패 절대 금지 (memory feedback_data_collection_verification_mandatory):
    try/finally + appended_n stderr 명시.
    """
    now = datetime.now(KST)
    ts = run_at_iso or now.isoformat()
    path = _output_path(now, root=output_root)

    appended = 0
    skipped = 0
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "a", encoding="utf-8") as f:
            for s in stocks:
                ticker = s.get("ticker")
                if not ticker:
                    skipped += 1
                    continue
                entry = {"ts": ts}
                for k in _SNAPSHOT_FIELDS:
                    v = s.get(k)
                    if v is not None:
                        entry[k] = v
                f.write(json.dumps(entry, ensure_ascii=False) + "\n")
                appended += 1
        print(
            f"[quarterly_history] appended n={appended} skipped={skipped} → {path.name}",
            file=sys.stderr, flush=True,
        )
        return {"logged": True, "appended_n": appended, "skipped_n": skipped, "path": str(path)}
    except Exception as e:
        print(
            f"[quarterly_history] FAIL — {type(e).__name__}: {e}",
            file=sys.stderr, flush=True,
        )
        return {"logged": False, "appended_n": appended, "skipped_n": skipped, "path": str(path)}

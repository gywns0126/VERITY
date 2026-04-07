"""
종목 스캔 → Gemini HS 매핑 → 관세청 수출입 통계 → trade_analysis.json → 텔레그램 TOP3

실행 (프로젝트 루트):
  PYTHONUNBUFFERED=1 python -m api.workflows.export_trade_pipeline

텔레그램 생략: TRADE_PIPELINE_NO_TELEGRAM=1
TOP3 없을 때 실패 알림(옵트인): EXPORT_PIPELINE_TELEGRAM_ON_FAILURE=1
스캔 종목 수: TRADE_PIPELINE_TOP_SCAN=30 (기본)
Gemini 생략(스텁 HS): TRADE_SKIP_GEMINI=1

필요 환경변수(.env): GEMINI_API_KEY, PUBLIC_DATA_API_KEY,
  CUSTOMS_TRADE_BASE_CNTY(기본 ZZ), CUSTOMS_TRADE_SURGE_COUNTRIES, CUSTOMS_TRADE_SURGE_MOM_PCT,
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import json
import math
import os
import sys
from typing import Any, Dict, List

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from api.analyzers.export_hscode_mapper import map_stocks_to_hscode_batch
from api.collectors.customs_trade_stats import (
    build_stock_analysis,
    rank_top_export_stocks,
    run_customs_two_phase_analysis,
)
from api.collectors.trading_value_scanner import scan_top_trading_value
from api.config import (
    HSCODE_MAPPING_PATH,
    PUBLIC_DATA_API_KEY,
    TRADE_ANALYSIS_PATH,
    now_kst,
)
from api.notifications.telegram import send_export_trade_top3


def _sanitize_json_obj(obj: Any) -> Any:
    if isinstance(obj, float):
        if math.isnan(obj) or math.isinf(obj):
            return None
        return obj
    if isinstance(obj, dict):
        return {k: _sanitize_json_obj(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize_json_obj(v) for v in obj]
    if obj is not None and hasattr(obj, "item"):
        try:
            return _sanitize_json_obj(obj.item())
        except Exception:
            return obj
    return obj


def _simple_mapping(full: Dict[str, Dict[str, Any]]) -> Dict[str, Dict[str, str]]:
    out: Dict[str, Dict[str, str]] = {}
    for name, info in full.items():
        out[name] = {
            "product": str(info.get("product", "")),
            "hscode": str(info.get("hscode", "")),
        }
    return out


def run_export_trade_pipeline(
    top_scan: int = 30,
    telegram: bool = True,
) -> Dict[str, Any]:
    print("[1/4] 거래대금 상위 스캔…", flush=True)
    stocks = scan_top_trading_value(top_n=top_scan)
    print(
        f"      → {len(stocks)}종목 (예: {stocks[0].name} / {stocks[0].trademoney_million_krw:,}백만원)",
        flush=True,
    )

    print("[2/4] Gemini HS 매핑…", flush=True)
    mapping_full = map_stocks_to_hscode_batch(stocks)
    print(f"      → 매핑 {len(mapping_full)}건", flush=True)

    mapping_payload = {
        "updated_at": now_kst().isoformat(),
        "by_name": _simple_mapping(mapping_full),
        "detail": mapping_full,
    }
    os.makedirs(os.path.dirname(HSCODE_MAPPING_PATH), exist_ok=True)
    with open(HSCODE_MAPPING_PATH, "w", encoding="utf-8") as f:
        json.dump(_sanitize_json_obj(mapping_payload), f, ensure_ascii=False, indent=2)

    stock_rows: List[Dict[str, Any]] = []
    monthly_note = ""

    if not PUBLIC_DATA_API_KEY:
        monthly_note = "PUBLIC_DATA_API_KEY 미설정 — 관세청 API 건너뜀"
        print(f"[3/4] {monthly_note}", flush=True)
        stock_rows = build_stock_analysis(mapping_full, pd.DataFrame())
    else:
        print("[3/4] 관세청 수출입 통계 수집·분석… (다소 시간 소요)", flush=True)
        try:
            monthly_df, stock_rows = run_customs_two_phase_analysis(mapping_full)
        except Exception as e:
            monthly_note = f"관세청 API 오류: {e}"
            print(f"      ⚠ {monthly_note}", flush=True)
            stock_rows = build_stock_analysis(mapping_full, pd.DataFrame())

    top3 = rank_top_export_stocks(stock_rows, top_k=3)

    analysis_out = {
        "generated_at": now_kst().isoformat(),
        "pipeline_note": monthly_note or None,
        "top3_export_momentum": [
            {
                "name": r["name"],
                "ticker": r.get("ticker"),
                "product": r.get("product"),
                "hscode": r.get("hscode"),
                "latest_yymm": r.get("latest_yymm"),
                "mom_export_pct": r.get("mom_export_pct"),
                "yoy_export_pct": r.get("yoy_export_pct"),
                "score": r.get("score"),
                "surge_country_breakdown": r.get("surge_country_breakdown"),
            }
            for r in top3
        ],
        "stocks": _sanitize_json_obj(stock_rows),
    }
    analysis_out = _sanitize_json_obj(analysis_out)

    os.makedirs(os.path.dirname(TRADE_ANALYSIS_PATH), exist_ok=True)
    with open(TRADE_ANALYSIS_PATH, "w", encoding="utf-8") as f:
        json.dump(analysis_out, f, ensure_ascii=False, indent=2)
    print(f"[4/4] 저장 완료: {TRADE_ANALYSIS_PATH}", flush=True)

    if telegram:
        if top3:
            send_export_trade_top3(top3, analysis_out.get("pipeline_note"))
        else:
            print("[4/4] 수출 TOP3 없음 → 텔레그램 생략", flush=True)
            _fail_tg = os.environ.get("EXPORT_PIPELINE_TELEGRAM_ON_FAILURE", "").lower() in (
                "1",
                "true",
                "yes",
            )
            if _fail_tg:
                from api.notifications.telegram import send_message

                note = (monthly_note or analysis_out.get("pipeline_note") or "").strip()
                body = note[:200] if note else "데이터 없음"
                send_message(
                    f"<b>📦 수출 파이프라인</b>\n"
                    f"<i>TOP3 미생성 (옵트인 알림)</i>\n\n{body}"
                )

    return analysis_out


if __name__ == "__main__":
    _no_tg = os.environ.get("TRADE_PIPELINE_NO_TELEGRAM", "").lower() in ("1", "true", "yes")
    _top = int(os.environ.get("TRADE_PIPELINE_TOP_SCAN", "30"))
    run_export_trade_pipeline(top_scan=_top, telegram=not _no_tg)

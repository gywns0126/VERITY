"""
종목 스캔 → Gemini HS 매핑 → 관세청 수출입 통계 → trade_analysis.json → 텔레그램 TOP3

실행 (프로젝트 루트):
  PYTHONUNBUFFERED=1 python -m api.workflows.export_trade_pipeline

텔레그램 생략: TRADE_PIPELINE_NO_TELEGRAM=1
TOP3 없을 때 실패 알림(옵트인): EXPORT_PIPELINE_TELEGRAM_ON_FAILURE=1
스캔 종목 수: TRADE_PIPELINE_TOP_SCAN=30 (기본)
Gemini 생략(스텁 HS): TRADE_SKIP_GEMINI=1

필요 환경변수(.env): GEMINI_API_KEY(없으면 HS 스텁), PUBLIC_DATA_API_KEY,
  CUSTOMS_TRADE_BASE_CNTY(기본 ZZ), CUSTOMS_TRADE_SURGE_COUNTRIES, CUSTOMS_TRADE_SURGE_MOM_PCT,
  TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID
"""
from __future__ import annotations

import json
import math
import os
import sys
import time
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
    # 🚨 단계별 계측 (2026-08-09). 8/4·8/5·8/6 이 30분 timeout 에 걸려 cancelled 인데
    #   8/7 은 12분에 끝났다. 어느 단계가 그 차이를 만드는지 로그로 알 수 없었다.
    #   계측 없는 실패는 오진을 낳는다 — timeout 을 올리기 전에 원인부터 특정한다.
    stage_sec: Dict[str, float] = {}
    _t0 = time.perf_counter()

    print("[1/4] 거래대금 상위 스캔…", flush=True)
    stocks = scan_top_trading_value(top_n=top_scan)
    if not stocks:
        raise RuntimeError("거래대금 상위 스캔 결과가 비었습니다.")
    ex = stocks[0]
    stage_sec["scan"] = round(time.perf_counter() - _t0, 1)
    print(
        f"      → {len(stocks)}종목 (예: {ex.name} / {ex.trademoney_million_krw:,}백만원)"
        f" [{stage_sec['scan']}s]",
        flush=True,
    )

    print("[2/4] Gemini HS 매핑…", flush=True)
    _t = time.perf_counter()
    mapping_full = map_stocks_to_hscode_batch(stocks)
    stage_sec["gemini_mapping"] = round(time.perf_counter() - _t, 1)
    print(f"      → 매핑 {len(mapping_full)}건 [{stage_sec['gemini_mapping']}s]", flush=True)

    # 🚨 전량 실패 가드 (#46). 1단계가 종목을 확보했는데 매핑이 0건이면 Gemini 전량
    #   실패다. 이대로 두면 stocks=[] 인 trade_analysis.json 을 정상 종료로 저장해
    #   신선도 보드가 통과시킨다. 산출 0건이 정상일 수 있는 증분 피드와 달리 여기는
    #   입력이 보장된 스냅샷이라 0건 = 사고다.
    if not mapping_full:
        raise RuntimeError(
            f"HS 매핑 전량 실패 — 입력 {len(stocks)}종목 대비 매핑 0건. "
            "산출을 갱신하지 않고 실패로 종료한다."
        )

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

    _t = time.perf_counter()
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
    stage_sec["customs"] = round(time.perf_counter() - _t, 1)
    print(f"      → 종목행 {len(stock_rows)}건 [{stage_sec['customs']}s]", flush=True)

    # 매핑은 됐는데 종목행이 0 = 산식 문제다(데이터 부재 아님). 조용히 빈 파일을
    # 저장하지 않는다 — 이 구분이 안 되어 있어 "왜 stocks 가 0인지" 를 매번 손으로 팠다.
    if not stock_rows:
        raise RuntimeError(
            f"종목 분석 전량 실패 — 매핑 {len(mapping_full)}건 대비 종목행 0건. "
            "데이터 부재가 아니라 산식 문제로 판정한다."
        )

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

    # 단계별 소요 — 30분 timeout 원인 특정용. 산출에 남겨 회차 간 비교가 되게 한다.
    # (sanitize 이후에 넣는다 — 값이 float 라 변환 대상이 아니고, total 이 여기서 확정된다.)
    stage_sec["total"] = round(time.perf_counter() - _t0, 1)
    analysis_out["stage_seconds"] = dict(stage_sec)

    os.makedirs(os.path.dirname(TRADE_ANALYSIS_PATH), exist_ok=True)
    with open(TRADE_ANALYSIS_PATH, "w", encoding="utf-8") as f:
        json.dump(analysis_out, f, ensure_ascii=False, indent=2)
    print(f"[4/4] 저장 완료: {TRADE_ANALYSIS_PATH}", flush=True)
    print(
        "[계측] " + " · ".join(f"{k}={v}s" for k, v in stage_sec.items())
        + f"  (timeout-minutes=30 = 1800s)",
        flush=True,
    )

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
    # 🚨 종료코드를 명시한다 (#46). 옛 코드는 반환값을 버려서 어떤 실패든 exit 0 이었다.
    try:
        run_export_trade_pipeline(top_scan=_top, telegram=not _no_tg)
    except Exception as _e:
        print(f"[export_trade] outcome=fail {type(_e).__name__}: {_e}", file=sys.stderr)
        sys.exit(1)
    sys.exit(0)

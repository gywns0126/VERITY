"""krx_mktcap_snapshot — KRX 공식 시가총액·상장주식수 스냅샷 (PER/PBR 자체계산 입력).

2026-06-19 신설. yfinance KR trailingPE/priceToBook=None 한계 돌파 — KRX OpenAPI 공식 MKTCAP ÷
DART 순이익·자기자본으로 PER/PBR 자체계산. 이 스냅샷이 그 시총 입력. 빌더(stock_report_public)는
'외부호출 0' 원칙이라 이 네트워크 스텝이 data/krx_mktcap.json 산출 → 빌더가 읽음(순수 변환 유지).

소스 = krx_openapi.krx_stk_ksq_rows_sorted_by_trading_value (sto/stk_bydd_trd + ksq_bydd_trd, KRX_API_KEY).
  KIS 무관(RULE1 안전, 별도 키). daily_analysis_full 에서 stock_report_public_builder 직전 실행.
출력 = data/krx_mktcap.json {_meta, map: {ticker: {mktcap, close, shares}}}. 발행 불요(중간 산출).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
OUTPUT_PATH = os.path.join(_ROOT, "data", "krx_mktcap.json")


def _int(v):
    try:
        return int(float(str(v).replace(",", "").strip()))
    except (TypeError, ValueError):
        return 0


def main() -> int:
    ok = False
    try:
        from api.collectors.krx_openapi import krx_stk_ksq_rows_sorted_by_trading_value

        bas_dd, rows = krx_stk_ksq_rows_sorted_by_trading_value()
        out = {}
        for r in rows or []:
            tk = str(r.get("ISU_SRT_CD") or r.get("ISU_CD") or "").strip()
            if not (len(tk) == 6 and tk.isdigit()):
                continue
            mktcap = _int(r.get("MKTCAP"))
            if mktcap <= 0:
                continue
            out[tk] = {"mktcap": mktcap, "close": _int(r.get("TDD_CLSPRC")), "shares": _int(r.get("LIST_SHRS"))}

        if not out and os.path.isfile(OUTPUT_PATH):
            print("[krx_mktcap] 0 rows — 기존 snapshot 보존", file=sys.stderr)
            ok = True
            return 0

        doc = {
            "_meta": {
                "generated_at": datetime.now(KST).isoformat(),
                "bas_dd": bas_dd,
                "count": len(out),
                "source": "KRX OpenAPI sto/stk_bydd_trd + ksq_bydd_trd (MKTCAP·LIST_SHRS)",
            },
            "map": out,
        }
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        print(f"[krx_mktcap] logged=True · {len(out)} 종목 시총 (basDd {bas_dd}) -> "
              f"{os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[krx_mktcap] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[krx_mktcap] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())

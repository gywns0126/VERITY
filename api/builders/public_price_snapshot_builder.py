"""public_price_snapshot_builder — 공개 가격 스냅샷 (히트맵 가격% 토글 입력).

2026-06-21 신설. AlphaNest 공개 히트맵(PublicHeatmap) 의 '가격%' 토글은 종목별 당일 등락률을
필요로 하나, stock_report_public.json 에는 가격/등락률이 없음(시총·재무 사실만). 이 빌더가
당일 등락률만 추린 경량 스냅샷을 산출 → Blob/VERITY-data 발행 → 히트맵 priceUrl 소비.

소스 = data/krx_mktcap.json {map: {ticker: {mktcap, close, shares, chg}}} — krx_mktcap_snapshot(네트워크 step,
  KRX OpenAPI, KIS 무관 RULE1 안전)가 직전 산출. 본 빌더는 '외부호출 0' 순수 변환(KIS 0).
출력 = data/public_price_snapshot.json {_meta, prices: {ticker: 등락률_float}}.
  히트맵 소비 형태: jget 이 d.prices 를 읽고, 값=숫자(등락률) 또는 {change_pct} 둘 다 허용 → 숫자로 emit.

RULE 7 = 외부 시장 사실(KRX 당일 등락률)만. 자체 점수·등급 0.
RULE 8 = 신규 발행 산출물 — publish-data action.yml allowlist 등재 의무([[feedback_publish_data_file_list_audit]]).
"""
from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

KST = timezone(timedelta(hours=9))
_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SRC_PATH = os.path.join(_ROOT, "data", "krx_mktcap.json")
OUTPUT_PATH = os.path.join(_ROOT, "data", "public_price_snapshot.json")


def main() -> int:
    ok = False
    try:
        if not os.path.isfile(SRC_PATH):
            print(f"[price_snapshot] krx_mktcap.json 없음 — skip (krx_mktcap_snapshot 선행 필요)", file=sys.stderr)
            print("[price_snapshot] logged=False", file=sys.stderr)
            return 0

        with open(SRC_PATH, "r", encoding="utf-8") as f:
            src = json.load(f)

        cap_map = (src.get("map") or {}) if isinstance(src, dict) else {}
        prices = {}
        for tk, e in cap_map.items():
            if not (isinstance(tk, str) and len(tk) == 6 and tk.isdigit() and isinstance(e, dict)):
                continue
            chg = e.get("chg")
            if chg is None:
                continue
            try:
                prices[tk] = round(float(chg), 2)
            except (TypeError, ValueError):
                continue

        if not prices and os.path.isfile(OUTPUT_PATH):
            print("[price_snapshot] 0 prices — 기존 snapshot 보존", file=sys.stderr)
            ok = True
            return 0

        src_meta = src.get("_meta") or {} if isinstance(src, dict) else {}
        doc = {
            "_meta": {
                "generated_at": datetime.now(KST).isoformat(),
                "bas_dd": src_meta.get("bas_dd"),
                "count": len(prices),
                "source": "KRX OpenAPI 당일 등락률(FLUC_RT) via krx_mktcap.json · 일 1회 스냅샷",
                "note": "당일 등락률(%) 사실만 · 자체 점수 아님(RULE7)",
            },
            "prices": prices,
        }
        with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
            json.dump(doc, f, ensure_ascii=False)
        print(f"[price_snapshot] logged=True · {len(prices)} 종목 등락률 (basDd {src_meta.get('bas_dd')}) -> "
              f"{os.path.relpath(OUTPUT_PATH, _ROOT)}", file=sys.stderr)
        ok = True
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[price_snapshot] FAILED: {e!r}", file=sys.stderr)
        return 1
    finally:
        if not ok:
            print("[price_snapshot] logged=False", file=sys.stderr)


if __name__ == "__main__":
    sys.exit(main())

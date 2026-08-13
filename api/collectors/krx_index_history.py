# -*- coding: utf-8 -*-
"""krx_index_history — KOSPI 일별 종가 이력 (L1 원장).

2026-08-13 신설. 포트폴리오 백테스트(PREREG_PORTFOLIO_BACKTEST_2026_08_13)의 벤치마크.

🚨 왜 일별인가: Calmar·MDD 를 리밸런스 빈도(20/60일)로 재면 **낙폭이 과소평가된다** —
구간 내 저점을 못 본다. win condition 이 MDD <20% 이므로 이 과소평가는 판정을 뒤집을 수 있다.
포트폴리오는 일별 마크투마켓, 벤치마크도 같은 빈도여야 상하방 포착률이 성립한다.

소스 = KRX OpenAPI `idx/kospi_dd_trd` (basDd 지정 과거 조회 — 2020-01 검증 완료).
날짜당 1콜이라 2020-01~2026-04 약 1,560 영업일. DART 쿼터 무관.
출력 = `data/metadata/kospi_daily.jsonl` {"d": 20200102, "close": 2175.17}
재개 가능 — 이미 수집한 날짜는 건너뛴다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta
from typing import Dict, Optional, Set

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.collectors.krx_openapi import _request_krx  # noqa: E402
from api.config import DATA_DIR  # noqa: E402

OUT_PATH = os.path.join(DATA_DIR, "metadata", "kospi_daily.jsonl")
SLEEP_SEC = 0.25
_INDEX_NAME = "코스피"


def _done(path: str) -> Set[int]:
    seen: Set[int] = set()
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        seen.add(int(json.loads(line)["d"]))
                    except (json.JSONDecodeError, KeyError, ValueError):
                        continue
    except OSError:
        pass
    return seen


def _fetch(dd: str) -> Optional[float]:
    r = _request_krx("idx/kospi_dd_trd", dd)
    if r.get("status") != "ok":
        return None
    for row in (r.get("rows") or []):
        if str(row.get("IDX_NM") or "").strip() == _INDEX_NAME:
            try:
                return float(str(row["CLSPRC_IDX"]).replace(",", ""))
            except (KeyError, ValueError):
                return None
    return None


def run(start: str, end: str, out_path: str = OUT_PATH) -> Dict[str, object]:
    t0 = time.time()
    d0 = date(int(start[:4]), int(start[4:6]), int(start[6:8]))
    d1 = date(int(end[:4]), int(end[4:6]), int(end[6:8]))
    already = _done(out_path)
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    written = holiday = 0
    d = d0
    with open(out_path, "a", encoding="utf-8") as f:
        while d <= d1:
            if d.weekday() >= 5:                 # 주말 = 호출 안 함
                d += timedelta(days=1)
                continue
            dd = d.strftime("%Y%m%d")
            if int(dd) in already:
                d += timedelta(days=1)
                continue
            v = _fetch(dd)
            if v is not None:
                f.write(json.dumps({"d": int(dd), "close": v}) + "\n")
                written += 1
                if written % 200 == 0:
                    f.flush()
                    print(f"  {dd} · {written}일 · {time.time() - t0:.0f}s", flush=True)
            else:
                holiday += 1                     # 휴장 — 기록하지 않는다(달력 왜곡 방지)
            time.sleep(SLEEP_SEC)
            d += timedelta(days=1)

    # 🚨 [[feedback_silent_total_failure_guard]] — 대상이 있는데 0건이면 성공 종료 금지
    status = "ok"
    if written == 0 and holiday > 20:
        status = "total_failure"
    return {"status": status, "written": written, "non_trading": holiday,
            "elapsed_sec": round(time.time() - t0, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="20191201")
    ap.add_argument("--end", default="20260831")
    a = ap.parse_args()
    r = run(a.start, a.end)
    if r["status"] == "total_failure":
        print(f"[kospi_daily] 🚨 전량 실패 (비거래일 {r['non_trading']})", file=sys.stderr)
        return 1
    print(f"[kospi_daily] {r['written']}일 신규 · 비거래 {r['non_trading']} · {r['elapsed_sec']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

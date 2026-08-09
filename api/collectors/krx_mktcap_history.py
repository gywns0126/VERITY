# -*- coding: utf-8 -*-
"""krx_mktcap_history — KRX 공식 시가총액·상장주식수 **과거 월말** 수집 (L1 원장).

2026-08-09 신설. 왜: 안심점수 100점 중 PER 20 · PBR 15 · 배당 12 = 47점이
PIT 재현 불가라 8/9 검정이 53점만 다뤘다([[project_safety_score_backtest_2026_08_09]]).
그 47점을 재현하려면 **리밸런스 시점의 시가총액**이 필요하다.

🚨 이 모듈은 **수집만 한다. 검정하지 않는다.** 전체 100점 검정은 별도 사전등록 대상이다.

## 왜 이 소스인가 (다른 경로를 먼저 실호출로 확인했다)

| 후보 | 실호출 결과 |
|---|---|
| pykrx `get_market_fundamental_by_ticker` | KRX 웹 응답 형식 변경/차단 — JSON 파싱 실패 |
| KRX 웹 `getJsonData.cmd` MDCSTAT03501 | HTTP 400 |
| KRX **OpenAPI** 18 엔드포인트 | 펀더멘털 엔드포인트 없음. 단 `bydd_trd` 가 MKTCAP·LIST_SHRS 를 준다 ✅ |
| DART 주식총수(`stockTotqySttus`) | 정상이나 종목·연도당 1콜 = 1.2만콜 |

`sto/stk_bydd_trd`(유가) + `sto/ksq_bydd_trd`(코스닥)는 **basDd 지정으로 과거 조회가 되고**
(2020-01-31 실검증) 한 콜이 그날 전종목을 준다. 79 월말 × 2시장 = **158콜**.
DART 쿼터를 전혀 쓰지 않는다([[project_dart_api_2026_constraints]] 20K/일 보호).

## PIT 정합

MKTCAP·LIST_SHRS 는 **그날 장 마감 실측치**다. 미래 정보가 섞일 여지가 없다.
분모(자본총계·순이익)만 공시 지연을 적용하면 된다 — 그건 소비 측 책임이다.

출력 = `data/metadata/krx_mktcap_history.jsonl` (append, 날짜 단위 재개 가능)
  {"d": 20200131, "t": "005930", "mc": <시총원>, "sh": <상장주식수>, "c": <종가>, "m": "KOSPI"}
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import date, timedelta
from typing import Dict, List, Optional, Set, Tuple

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from api.collectors.krx_openapi import _request_krx  # noqa: E402
from api.config import DATA_DIR  # noqa: E402

OUT_PATH = os.path.join(DATA_DIR, "metadata", "krx_mktcap_history.jsonl")
MARKETS: Tuple[Tuple[str, str], ...] = (
    ("sto/stk_bydd_trd", "KOSPI"),
    ("sto/ksq_bydd_trd", "KOSDAQ"),
)
# 월말이 휴장이면 직전 영업일로 물러난다. 실제 채택일을 행에 남긴다(감사 가능).
MAX_WALKBACK = 7
SLEEP_SEC = 0.3          # KRX OpenAPI 예의. 158콜이라 총 ~1분 추가


def _pint(s: object) -> Optional[int]:
    try:
        return int(float(str(s).replace(",", "").strip()))
    except (ValueError, TypeError, AttributeError):
        return None


def _prev_day(yyyymmdd: str) -> str:
    d = date(int(yyyymmdd[:4]), int(yyyymmdd[4:6]), int(yyyymmdd[6:8])) - timedelta(days=1)
    return d.strftime("%Y%m%d")


def month_ends(start: str, end: str) -> List[str]:
    """start~end 사이 달력 월말 목록. 유니버스 시점과 같은 규칙."""
    out: List[str] = []
    y, m = int(start[:4]), int(start[4:6])
    ey, em = int(end[:4]), int(end[4:6])
    while (y, m) <= (ey, em):
        ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
        last = date(ny, nm, 1) - timedelta(days=1)
        out.append(last.strftime("%Y%m%d"))
        y, m = ny, nm
    return out


def done_dates(path: str) -> Set[int]:
    """이미 수집한 요청일. 🚨 행에 남는 건 실제 채택일이라 요청일을 따로 기록해야 재개가 맞는다."""
    seen: Set[int] = set()
    try:
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    r = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if r.get("req") is not None:
                    seen.add(int(r["req"]))
    except OSError:
        pass
    return seen


def fetch_one(path: str, req_dd: str) -> Tuple[Optional[str], List[Dict[str, object]]]:
    """요청일부터 최대 MAX_WALKBACK 일 물러나며 첫 ok 응답. (채택일, rows)."""
    dd = req_dd
    for _ in range(MAX_WALKBACK):
        r = _request_krx(path, dd)
        if r.get("status") == "ok":
            return dd, list(r.get("rows") or [])
        if r.get("status") in ("error", "forbidden") and r.get("http_status") in (401, 403):
            raise RuntimeError(f"KRX 권한 실패: {r.get('reason')}")
        dd = _prev_day(dd)
        time.sleep(SLEEP_SEC)
    return None, []


def run(start: str, end: str, out_path: str = OUT_PATH, limit: int = 0) -> Dict[str, object]:
    t0 = time.time()
    targets = month_ends(start, end)
    if limit:
        targets = targets[:limit]
    already = done_dates(out_path)
    todo = [d for d in targets if int(d) not in already]
    os.makedirs(os.path.dirname(out_path), exist_ok=True)

    written = 0
    per_date: Dict[str, int] = {}
    misses: List[str] = []
    with open(out_path, "a", encoding="utf-8") as f:
        for req_dd in todo:
            n_day = 0
            for api_path, mkt in MARKETS:
                used, rows = fetch_one(api_path, req_dd)
                if used is None:
                    misses.append(f"{req_dd}/{mkt}")
                    continue
                for row in rows:
                    t = str(row.get("ISU_CD") or "").strip()
                    mc, sh, c = (_pint(row.get("MKTCAP")), _pint(row.get("LIST_SHRS")),
                                 _pint(row.get("TDD_CLSPRC")))
                    # 🚨 시총 0/None = 거래정지·관리종목 등. 버리지 않고 그대로 남긴다
                    #    (소비 측에서 제외 사유를 세야 커버리지 신고가 정직해진다).
                    if not t or len(t) != 6:
                        continue
                    f.write(json.dumps({"req": int(req_dd), "d": int(used), "t": t,
                                        "mc": mc, "sh": sh, "c": c, "m": mkt},
                                       ensure_ascii=False) + "\n")
                    written += 1
                    n_day += 1
                time.sleep(SLEEP_SEC)
            per_date[req_dd] = n_day
            print(f"  {req_dd}: {n_day}종목 · 누적 {written:,} · {time.time() - t0:.0f}s", flush=True)

    # 🚨 [[feedback_silent_total_failure_guard]] — 대상이 있는데 0건이면 성공으로 끝내지 않는다
    status = "ok"
    if todo and written == 0:
        status = "total_failure"
    return {"status": status, "targets": len(targets), "todo": len(todo),
            "written": written, "misses": misses, "per_date": per_date,
            "elapsed_sec": round(time.time() - t0, 1)}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="201912")
    ap.add_argument("--end", default="202608")
    ap.add_argument("--limit", type=int, default=0)
    a = ap.parse_args()
    r = run(a.start, a.end, limit=a.limit)
    if r["status"] == "total_failure":
        print(f"[krx_mktcap_history] 🚨 대상 {r['todo']}일인데 0건 — 전량 실패", file=sys.stderr)
        return 1
    print(f"[krx_mktcap_history] {r['written']:,}행 · 대상 {r['targets']}월 "
          f"· 신규 {r['todo']}월 · {r['elapsed_sec']}s")
    if r["misses"]:
        print(f"[krx_mktcap_history] 미수집 {len(r['misses'])}건: {r['misses'][:8]}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

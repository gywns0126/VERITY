# -*- coding: utf-8 -*-
"""비12월 결산 법인의 quarter_end 소급 정정 — **API 호출 0**. 2026-08-22 신설.

## 왜

`_quarter_end_iso` 가 12월 결산을 가정해 `{연도}-{reprt_code별 고정 mmdd}` 를 썼다.
비12월 결산 법인은 회계연도 종료가 달라 **매 수집이 같은 칸에 덮어쓰기만** 했다.
실측 021820(세원정공, 6월 결산): 2026-06~08 두 달간 12번 수집했는데 전부 `2025-12-31`
이라 고유 분기가 3개뿐이고 조인의 `MIN_QUARTERS=4` 에서 탈락했다.

수집기는 오늘 고쳤다(결산월 주입). 이 스크립트는 **이미 쌓인 과거 행**을 정정한다.

## 왜 API 가 필요 없나

옛 산식이 `{rd}-{suffix}` 였고 `rd`(연도)는 저장된 quarter_end 의 앞 4자에 그대로 남아 있다.
따라서 `연도 + shift_mmdd(reprt_code별 mmdd, 결산월)` 로 **오프라인 재계산**이 된다.

🚨 **단, mmdd 가 `_REPRT_END_MMDD[reprt_code]` 와 정확히 일치하는 행만 고친다.**
그 외는 `report_date` 가 완전한 날짜여서 그대로 반환된 행이거나 오염 행이므로 손대지 않는다.
(잘못 고치면 맞는 값을 망친다 — 오늘 산식 검증에서 그 위험을 한 번 겪었다.)

## 범위

전수 조회(DART company.json acc_mt, 2,772종목) 결과 **비12월은 53종목(1.9%)**.
98.1% 는 현행이 맞으므로 건드리지 않는다.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import Counter

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, _ROOT)
from api.builders.dart_batch_builder import _REPRT_END_MMDD, _shift_mmdd  # noqa: E402

SNAP = os.path.join(_ROOT, "data", "dart_quarterly_snapshots.jsonl")
FISCAL = os.path.join(_ROOT, "data", "kr_fiscal_month.json")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    fm = (json.load(open(FISCAL, encoding="utf-8")) or {}).get("map") or {}
    non12 = {t: m for t, m in fm.items() if m != "12"}
    print(f"[fix_qe] 결산월 맵 {len(fm):,} · 비12월 {len(non12)}종목")

    out_lines = []
    fixed = 0
    skipped_shape = 0
    touched = Counter()
    with open(SNAP, encoding="utf-8") as f:
        for line in f:
            raw = line.rstrip("\n")
            if not raw.strip():
                continue
            try:
                r = json.loads(raw)
            except ValueError:
                out_lines.append(raw)
                continue
            tk = str(r.get("ticker") or "")
            fmn = non12.get(tk)
            qe = str(r.get("quarter_end") or "")
            rc = str(r.get("reprt_code") or "")
            if not fmn or len(qe) != 10 or not rc:
                out_lines.append(raw)
                continue
            expect_old = _REPRT_END_MMDD.get(rc)
            if not expect_old or qe[5:] != expect_old:
                # 완전 날짜 유래이거나 오염 행 — 손대지 않는다
                skipped_shape += 1
                out_lines.append(raw)
                continue
            new_mmdd = _shift_mmdd(expect_old, fmn)
            if new_mmdd == expect_old:
                out_lines.append(raw)
                continue
            r["quarter_end"] = f"{qe[:4]}-{new_mmdd}"
            r["_qe_fixed"] = "fiscal_month"      # 🚨 정정 흔적을 남긴다(조용한 변경 금지)
            fixed += 1
            touched[tk] += 1
            out_lines.append(json.dumps(r, ensure_ascii=False))

    print(f"[fix_qe] 정정 {fixed:,}행 · 형태 불일치로 보존 {skipped_shape:,}행 "
          f"· 영향 종목 {len(touched)}")
    for tk, n in touched.most_common(8):
        print(f"    {tk} 결산월 {non12[tk]} · {n}행")
    if a.dry_run:
        print("[fix_qe] dry-run — 파일 미변경")
        return 0
    if not fixed:
        print("[fix_qe] 정정 0 — 변경 없음")
        return 0
    shutil.copy2(SNAP, SNAP + ".bak")
    tmp = SNAP + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(out_lines) + "\n")
    os.replace(tmp, SNAP)
    print(f"[fix_qe] 기록 완료 (백업 {os.path.basename(SNAP)}.bak)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

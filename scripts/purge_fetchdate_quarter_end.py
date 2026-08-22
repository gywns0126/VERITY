# -*- coding: utf-8 -*-
"""수집일이 quarter_end 로 유입된 행 정리 — **API 호출 0**. 2026-08-22 신설.

## 왜

`_quarter_end_iso` 는 산출 불가 시 `fetched_at[:10]`(수집일)을 쓰는 폴백이 있었다.
2026-08-07 에 그 폴백을 막았지만(빈 문자열 반환 → caller 가 행을 기록하지 않음)
**그 이전에 쌓인 행이 남아 있다.** 코드 결함은 이미 없고 데이터 잔재다.

실측 2026-08-22 — 2,631행(1.7%)이 `quarter_end == fetched_at` **100% 일치**:
  05-17 1,867(reprt_code=None) · 06-07 298 · 07-24 96 · 08-02 90 …

## 지워도 되는 근거 (열거 먼저 — RULE 13)

- 하류가 **이미 전부 버린다**: 공개 빌더 `_allowed_ends` 필터(매 빌드 "non-fiscal 2,631" 보고) ·
  `fscore_delta`/`quarterly_revenue` 는 quarter_end 매칭 실패로 자연 무시.
  → 지워도 **동작이 바뀌지 않는다.**
- 이 행이 유일 소스인 티커 42개 중 **34개가 우선주 계열**(본주와 재무 동일) ·
  나머지도 분기말 미상 순이익 1점뿐이라 YoY 에 못 쓴다.
- 분기말을 모르면 순이익도 못 쓴다 — 어느 분기 값인지 알 수 없다.

🚨 **판정은 종목별 결산월 기준**이다(`kr_fiscal_month.json`). 12월 결산 고정 집합으로
판정하면 비12월 결산 법인의 정상 행을 오염으로 지운다.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
from collections import Counter

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SNAP = os.path.join(_ROOT, "data", "dart_quarterly_snapshots.jsonl")
FISCAL = os.path.join(_ROOT, "data", "kr_fiscal_month.json")
_MMDD = {"01": "31", "02": "28", "03": "31", "04": "30", "05": "31", "06": "30",
         "07": "31", "08": "31", "09": "30", "10": "31", "11": "30", "12": "31"}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()

    fm = (json.load(open(FISCAL, encoding="utf-8")) or {}).get("map") or {}

    def allowed(tk: str) -> set:
        f = str(fm.get(tk) or "12")
        out = set()
        for off in (3, 6, 9, 12):
            m = (int(f) + off - 1) % 12 + 1
            out.add(f"{m:02d}-{_MMDD[f'{m:02d}']}")
        return out

    keep, drop = [], []
    why = Counter()
    with open(SNAP, encoding="utf-8") as f:
        for line in f:
            raw = line.rstrip("\n")
            if not raw.strip():
                continue
            try:
                r = json.loads(raw)
            except ValueError:
                keep.append(raw)
                continue
            tk = str(r.get("ticker") or "")
            qe = str(r.get("quarter_end") or "")
            fa = str(r.get("fetched_at") or "")[:10]
            if len(qe) == 10 and qe[5:] not in allowed(tk):
                # 🚨 수집일과 일치할 때만 지운다 — 그 외 이상 날짜는 원인이 달라 보존한다
                if qe == fa:
                    drop.append(r)
                    why[qe] += 1
                    continue
                why["기타(보존)"] += 1
            keep.append(raw)

    print(f"[purge_qe] 삭제 대상 {len(drop):,} · 보존 {len(keep):,}")
    print(f"  상위 사유: {dict(why.most_common(6))}")
    if a.dry_run:
        print("[purge_qe] dry-run — 파일 미변경")
        return 0
    if not drop:
        print("[purge_qe] 삭제 0 — 변경 없음")
        return 0
    shutil.copy2(SNAP, SNAP + ".bak")
    tmp = SNAP + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write("\n".join(keep) + "\n")
    os.replace(tmp, SNAP)
    print(f"[purge_qe] 정리 완료 (백업 {os.path.basename(SNAP)}.bak)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

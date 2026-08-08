#!/usr/bin/env python3
"""KR 지분구조 drip 백필 — 공개 리포트 ownership 섹션 전 종목 확대.

PM 2026-08-08 "자동으로 안채워진 국장 정보 중에서 비어있거나, 비교적 뒤쳐진 데이터들이
있다면 이후에 자동으로 모아지게 해".

발단: 커버리지 래칫(feaae26)이 KR ownership **18.8%** 를 다음 표적으로 지목했다.
  원인은 소스 부재가 아니라 **범위**였다 —
  · 종전 ownership 소스 = 공정위 기업집단포털 → 대규모기업집단 소속사 ~346개사가 상한.
  · group_structure 수집기는 DART hyslrSttus 를 이미 쓰지만 **운영풀 20종목** 에만 돈다.
  · 실호출 확인(2026-08-08): 088910 동우팜투테이블 → 군산도시가스 25.44%(최대주주) ·
    김동수 17.49%. 즉 임의 상장사도 DART 가 정상 응답한다.

설계 = 기존 dart_quarterly_backfill_builder 의 drip 패턴을 그대로 따른다(신규 발명 금지):
  · 매 run CHUNK 만큼만 진행 → 결과 병합 저장 → cursor 영속. 다음 run 이 이어받는다.
  · 전 종목 완주 후 done → no-op(재조회 안 함). 신규 상장·사업연도 갱신 시 자동 재개.
  · DART 일일 한도(20K, [[project_dart_api_2026_constraints]]) 를 다른 소비자와 나눠 쓰므로
    보수적으로 잡는다. 종목당 정확히 1콜.

🚨 RULE 7 — DART 공시 사실만 적재(자체 산식·점수 0). 공개 리포트 allowlist 정합.
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, _ROOT)

from api.config import DART_API_KEY, DATA_DIR, now_kst  # noqa: E402

OUT_PATH = os.path.join(DATA_DIR, "kr_ownership.json")
CURSOR_PATH = os.path.join(DATA_DIR, "metadata", "kr_ownership_cursor.json")

# run 당 종목 수. 종목당 1콜이므로 곧 콜 수다.
# 300 = 1,795종목 기준 약 6일 완주. DART 20K/일을 dart_catalyst / quarterly_backfill 등과
# 나눠 쓰므로 여유를 크게 둔다 — 빨리 채우려다 다른 수집기를 굶기면 손해가 더 크다.
CHUNK = int(os.environ.get("OWNERSHIP_CHUNK", "300"))
# 최대주주 표시 상한 — 상위 지분자만 노출(합계·계 행 제외 후). 발행 크기 방어.
TOP_N = 6


def _load(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _universe() -> List[str]:
    """공개 리포트에 실린 KR 종목 = 채워야 할 대상. 리포트 밖 종목은 채워도 안 보인다."""
    doc = _load(os.path.join(DATA_DIR, "stock_report_public.json"), {})
    out = []
    for s in (doc.get("stocks") or []):
        tk = str((s or {}).get("ticker") or "")
        if len(tk) == 6 and tk.isdigit():
            out.append(tk)
    return sorted(set(out))


def _clean_rows(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """집계행(계·합계) 제거 + 지분율 파싱. DART 응답에 소계가 섞여 들어온다."""
    out = []
    for r in rows or []:
        nm = str(r.get("nm") or "").strip()
        if not nm or nm in ("계", "합계", "소계", "-"):
            continue
        try:
            rate = float(str(r.get("stock_rate") or "").replace(",", "").replace("%", ""))
        except (TypeError, ValueError):
            rate = None
        if rate is None:
            continue
        out.append({
            "name": nm,
            "relate": str(r.get("relate") or "").strip(),
            "pct": round(rate, 2),
        })
    out.sort(key=lambda x: -x["pct"])
    return out[:TOP_N]


def run() -> Dict[str, Any]:
    if not DART_API_KEY:
        print("[ownership_bf] DART_API_KEY 없음 — skip", file=sys.stderr)
        return {"skipped": True}

    from api.collectors.DartScout import fetch_major_shareholders
    from api.collectors.dart_corp_code import get_corp_code

    universe = _universe()
    if not universe:
        print("[ownership_bf] 유니버스 0 — 공개 리포트 부재? skip", file=sys.stderr)
        return {"skipped": True}

    store: Dict[str, Any] = _load(OUT_PATH, {}) or {}
    holders: Dict[str, Any] = store.get("holders") or {}
    cursor = _load(CURSOR_PATH, {}) or {}
    year = str(now_kst().year - 1)  # 사업보고서 = 전년도 기준

    # 사업연도가 바뀌면 커서를 되감아 자동 재개 (PM "이후에 자동으로")
    if cursor.get("year") != year:
        cursor = {"year": year, "idx": 0, "done": False}

    # 아직 못 채운 종목 우선 — 이미 채운 종목을 다시 긁지 않는다(한도 절약).
    pending = [tk for tk in universe if tk not in holders]
    if not pending:
        cursor.update({"idx": len(universe), "done": True})
        _save_cursor(cursor, len(universe), len(holders))
        print(f"[ownership_bf] done — {len(holders)}/{len(universe)}종목 보유, 신규 대상 0 (no-op)",
              file=sys.stderr)
        return {"done": True, "have": len(holders), "universe": len(universe)}

    batch = pending[:CHUNK]
    got, miss = 0, 0
    for tk in batch:
        try:
            cc = get_corp_code(tk)
            if not cc:
                miss += 1
                continue
            rows = _clean_rows(fetch_major_shareholders(cc, year))
            if rows:
                holders[tk] = {"top": rows, "year": year}
                got += 1
            else:
                miss += 1
        except Exception as e:  # noqa: BLE001
            miss += 1
            print(f"[ownership_bf] {tk} 실패: {e!r}", file=sys.stderr)

    store = {
        "_meta": {
            "generated_at": now_kst().isoformat(),
            "source": "DART 최대주주 현황(hyslrSttus) · 사업보고서 " + year,
            "note": "공시 사실만 · 자체 산식 0 (RULE 7)",
            "count": len(holders),
            "universe": len(universe),
        },
        "holders": holders,
    }
    os.makedirs(DATA_DIR, exist_ok=True)
    tmp = OUT_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(store, f, ensure_ascii=False)
    os.replace(tmp, OUT_PATH)

    remaining = len(pending) - len(batch)
    cursor.update({"idx": len(universe) - remaining, "done": remaining == 0})
    _save_cursor(cursor, len(universe), len(holders))
    print(f"[ownership_bf] logged=True · 이번 run {got}건 수집 / {miss} 미확보 · "
          f"누적 {len(holders)}/{len(universe)}종목 · 잔여 {remaining}", file=sys.stderr)
    return {"got": got, "miss": miss, "have": len(holders),
            "universe": len(universe), "remaining": remaining}


def _save_cursor(cursor: Dict[str, Any], universe_n: int, have_n: int) -> None:
    os.makedirs(os.path.dirname(CURSOR_PATH), exist_ok=True)
    cursor.update({"universe": universe_n, "have": have_n, "updated_at": now_kst().isoformat()})
    with open(CURSOR_PATH, "w", encoding="utf-8") as f:
        json.dump(cursor, f, ensure_ascii=False, indent=1)


def main() -> int:
    try:
        run()
        return 0
    except Exception as e:  # noqa: BLE001
        print(f"[ownership_bf] FAILED: {e!r}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

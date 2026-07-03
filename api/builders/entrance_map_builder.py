"""입구 지도 (Entrance Map) — AlphaNest 홈 진입 뷰.

"가진 것의 지도" — 이미 발행 중인 공개 데이터 자산들의 규모(count)·기준시각(generated_at)만
추출해 초경량 집계 JSON 1개로 재발행. 홈에서 원본(수 MB)을 직접 당기지 않기 위한 지도 전용 파일.

입력(read-only, 전부 이미 publish-data 등재된 공개 산출물):
  universe_search / stock_report_public / us_stock_report_public / dart_quarterly_public
  / insider_trades / us_insider_trades / disclosure_forensics / stock_flow_5d
  / securities_lending / sector_overview / validation_summary
출력: data/entrance_map.json (~1KB)

규율: 사실(개수·시각)만 — 점수/랭킹/추천 0 (RULE 7). LLM 0 (RULE 6).
      원본 없거나 파싱 실패 = 해당 항목 skip (부분 실패가 전체를 죽이지 않음).
"""
import json
import os
from datetime import datetime, timezone, timedelta
from typing import Any, Dict, Optional

_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_DATA = os.path.join(_ROOT, "data")
OUTPUT_PATH = os.path.join(_DATA, "entrance_map.json")

KST = timezone(timedelta(hours=9))

# (id, 파일명, count 추출 방식) — count_key: _meta.count 우선, 없으면 해당 최상위 list/dict 길이
SOURCES = [
    ("universe", "universe_search.json", "stocks"),
    ("stock_report", "stock_report_public.json", "stocks"),
    ("us_stock_report", "us_stock_report_public.json", "stocks"),
    ("quarterly", "dart_quarterly_public.json", "stocks"),
    ("insider_kr", "insider_trades.json", "stocks"),
    ("insider_us", "us_insider_trades.json", "stocks"),
    ("forensics", "disclosure_forensics.json", "stocks"),
    ("flow_5d", "stock_flow_5d.json", "flows"),
    ("lending", "securities_lending.json", "stocks"),
    ("sectors", "sector_overview.json", "sectors"),
]


def _load(name: str) -> Optional[Dict[str, Any]]:
    path = os.path.join(_DATA, name)
    if not os.path.exists(path):
        return None
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return None


def _count(doc: Dict[str, Any], key: str) -> Optional[int]:
    meta = doc.get("_meta") or {}
    c = meta.get("count")
    if isinstance(c, int) and c > 0:
        return c
    v = doc.get(key)
    if isinstance(v, (list, dict)):
        return len(v)
    return None


def _as_of(doc: Dict[str, Any]) -> Optional[str]:
    meta = doc.get("_meta") or {}
    for k in ("generated_at", "as_of", "collected_at"):
        v = meta.get(k) or doc.get(k)
        if v:
            return str(v)
    return None


def build() -> Dict[str, Any]:
    assets = []
    for asset_id, fname, count_key in SOURCES:
        doc = _load(fname)
        if not doc:
            continue
        entry: Dict[str, Any] = {"id": asset_id, "count": _count(doc, count_key), "as_of": _as_of(doc)}
        assets.append(entry)

    # 검증 원장 — 게이트 진척(사실)만. raw 성과 봉인 정책(validation_summary._note) 그대로 상속.
    vs = _load("validation_summary.json")
    gate = None
    if vs and isinstance(vs.get("gate"), dict):
        g = vs["gate"]
        gate = {
            "target_n": g.get("target_n"),
            "progress_pct": g.get("progress_pct"),
            "signals": len(vs.get("signals") or []),
            "as_of": vs.get("generated_at"),
        }

    return {
        "_meta": {
            "generated_at": datetime.now(KST).isoformat(),
            "source": "entrance_map_builder — 발행 중 공개 JSON 들의 count·기준시각 집계 (원본 전부 publish-data 등재)",
            "note": "사실(개수·시각)만 — 점수·랭킹·추천 0 (RULE 7)",
        },
        "assets": assets,
        "validation_gate": gate,
    }


def main() -> None:
    out = build()
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    n = len(out.get("assets") or [])
    print(f"[entrance_map] wrote {OUTPUT_PATH} — assets={n}, gate={'yes' if out.get('validation_gate') else 'no'}")


if __name__ == "__main__":
    main()

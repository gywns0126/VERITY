#!/usr/bin/env python3
"""
dart_business_overview_extract — 로컬 사업보고서 원문 코퍼스에서 「사업의 개요」 일괄 추출.

2026-08-23 신설. PM 지적 = "1,210종목 사업보고서 원문을 이미 받아놓고 「사업의 개요」를 안 뽑고 있다".

원천 = `data/dart_raw_cache/{corp_code}_{year}.json.gz` 의 `raw_text`
       (DartScout `_extract_section_from_rcept` 가 저장한 'II. 사업의 내용' 슬라이스, 60K 상한).
       🚨 이미 디스크에 있다 — 이 경로는 **네트워크 0 · DART 쿼터 0**.
       🚨 `dart_raw_cache/` 는 .gitignore 다 = **로컬 전용**. CI 에는 없다.
          그래서 산출물(`data/dart_business_overview.json`)이 추적 대상이고,
          CI 증분은 `kr_company_facts_backfill.py --axes overview` 가 맡는다(문서 fetch 발생).

파싱 규칙 = `api/analyzers/dart_business_overview.py` **단일 출처**. 여기 사본을 두지 않는다.

🚨 RULE 13 — 분모 먼저. `_meta.funnel` 이 단계별 (통과 N / 직전 단계 M)을 자기신고한다.
   반려는 사유별 개수 + 예시 종목으로 남긴다. "대부분/거의" 로 뭉개지 않는다.

usage: python scripts/dart_business_overview_extract.py [--max-chars 2500] [--dry-run]
"""
from __future__ import annotations

import argparse
import collections
import gzip
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_ROOT = str(Path(__file__).resolve().parent.parent)
sys.path.insert(0, _ROOT)

from api.analyzers.dart_business_overview import (  # noqa: E402
    CACHE_PATH as OUT_PATH,
    DEFAULT_MAX_CHARS,
    extract_overview,
    load_cache,
    row_from_doc,
    save_cache,
)

DATA_DIR = os.path.join(_ROOT, "data")
RAW_DIR = os.path.join(DATA_DIR, "dart_raw_cache")
MAPPING_PATH = os.path.join(DATA_DIR, "mapping.json")
NAMES_PATH = os.path.join(DATA_DIR, "kr_stock_names.json")


def _read_raw(path: str) -> Optional[Dict[str, Any]]:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError, EOFError):
        return None


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-chars", type=int, default=DEFAULT_MAX_CHARS,
                    help="종목당 본문 상한(문장 경계 절단)")
    ap.add_argument("--sample", type=int, default=None, help="앞 N개만 처리(스모크)")
    ap.add_argument("--dry-run", action="store_true", help="파일 쓰지 않고 분모만 보고")
    args = ap.parse_args()

    if not os.path.isdir(RAW_DIR):
        print(f"[biz-overview] {RAW_DIR} 없음 — 로컬 코퍼스 경로 전용", file=sys.stderr)
        return 1
    with open(MAPPING_PATH, encoding="utf-8") as f:
        mapping = json.load(f)             # {종목코드: corp_code}
    rev = {v: k for k, v in mapping.items()}
    names: Dict[str, str] = {}
    try:
        with open(NAMES_PATH, encoding="utf-8") as f:
            names = json.load(f)
    except (OSError, json.JSONDecodeError):
        pass

    files = sorted(f for f in os.listdir(RAW_DIR) if f.endswith(".json.gz"))
    if args.sample:
        files = files[: args.sample]

    cache = load_cache()
    rows: Dict[str, Dict[str, Any]] = dict(cache.get("rows") or {})
    n_files = len(files)
    n_mapped = n_read = n_new = n_kept = 0
    rejects: collections.Counter = collections.Counter()
    reject_ex: Dict[str, List[str]] = collections.defaultdict(list)
    unmapped: List[str] = []
    lens: List[int] = []

    for fn in files:
        corp = fn.split("_")[0]
        year = fn.split("_")[-1].replace(".json.gz", "")
        tk = rev.get(corp)
        if not tk:
            unmapped.append(corp)
            continue
        n_mapped += 1
        doc = _read_raw(os.path.join(RAW_DIR, fn))
        if not doc:
            rejects["file_unreadable"] += 1
            continue
        n_read += 1
        prev = rows.get(tk)
        if prev and str(prev.get("bsns_year") or "") > year:
            n_kept += 1                    # 더 최신 사업연도 행 보존
            continue
        row = row_from_doc(doc, corp, year, name=names.get(tk, ""), max_chars=args.max_chars)
        if row is None:
            res = extract_overview(doc.get("raw_text") or "", args.max_chars)
            r = (res.get("reason") or "unknown").split("(")[0]
            rejects[r] += 1
            if len(reject_ex[r]) < 4:
                reject_ex[r].append(f"{tk}/{names.get(tk, corp)}")
            continue
        rows[tk] = row
        n_new += 1
        lens.append(row["char_count"])

    lens.sort()

    def pct(p: float) -> int:
        return lens[int(len(lens) * p)] if lens else 0

    meta = dict(cache.get("_meta") or {})
    meta.update({
        "artifact": "dart_business_overview",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "source": "DART 사업보고서 II. 사업의 내용 › 1. 사업의 개요 (dart_raw_cache 재사용, 네트워크 0)",
        "extractor": "api/analyzers/dart_business_overview.py",
        "runner": "scripts/dart_business_overview_extract.py",
        "_method": "deterministic_regex_slice",
        "max_chars": args.max_chars,
        # 🚨 RULE 13 — 단계별 분모. "전부" 라고 쓰지 않는다.
        "funnel": {
            "raw_files": n_files,
            "ticker_mapped": n_mapped,
            "file_read": n_read,
            "extracted_this_run": n_new,
            "kept_newer_year": n_kept,
            "rows_total": len(rows),
            "rate_of_mapped": round(len(rows) / n_mapped * 100, 1) if n_mapped else 0.0,
        },
        "rejects": dict(rejects.most_common()),
        "reject_examples": dict(reject_ex),
        "unmapped_corp_n": len(unmapped),
        "char_p10_p50_p90": [pct(0.1), pct(0.5), pct(0.9)],
        "truncated_n": sum(1 for r in rows.values() if r.get("truncated")),
        "_partial": False,
    })
    print(f"[biz-overview] 원문 {n_files} → 티커매핑 {n_mapped} → 보유 {len(rows)} "
          f"(이번 run 신규 {n_new}, {meta['funnel']['rate_of_mapped']}% of mapped) · "
          f"반려 {dict(rejects.most_common(5))}", file=sys.stderr)
    print(f"[biz-overview] 길이 p10/p50/p90 = {meta['char_p10_p50_p90']} · 절단 {meta['truncated_n']}",
          file=sys.stderr)
    if args.dry_run:
        return 0
    save_cache({"_meta": meta, "rows": rows})
    print(f"[biz-overview] -> {os.path.relpath(OUT_PATH, _ROOT)} "
          f"({os.path.getsize(OUT_PATH)/1e6:.2f}MB)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())

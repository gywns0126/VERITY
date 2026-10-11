#!/usr/bin/env python3
"""Refresh only the public KR overview from local backfill rows (no collection).

Reuse the report builder's publication limit and existing sentence cutter; do not
run its main(), which writes other artifacts and can invoke a relation worker.
Missing/empty raw input fails without replacing the last public snapshot. Partial
input retains prior rows, and older filings cannot replace newer public sources.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
import tempfile
from datetime import datetime

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.analyzers.dart_business_overview import _cut_at_sentence
from api.builders.stock_report_public_builder import BIZ_OVERVIEW_PUBLISH_CHARS, DART, _now_kst
from api.intelligence.portfolio_public_sources import project_public_business_overviews

PUBLIC_FILE = "kr_business_overview_public.json"
SOURCE = "DART 사업보고서 II. 사업의 내용 › 1. 사업의 개요"


def _rows(document):
    if not isinstance(document, dict) or not isinstance(document.get("rows"), dict):
        raise ValueError("overview rows must be an object")
    if any(not isinstance(row, dict) for row in document["rows"].values()):
        raise ValueError("overview row must be an object")
    return document["rows"]


def build_public(raw, prior, listed):
    raw_rows, prior_rows = _rows(raw), _rows(prior)
    rows = dict(prior_rows)
    usable = empty = older = rejected = 0
    generated_at = _now_kst().isoformat()
    for ticker, row in raw_rows.items():
        text = row.get("text")
        if text is None or text == "" or (isinstance(text, str) and not text.strip()):
            empty += 1
            continue
        filed, receipt, year = (row.get(k) for k in ("rcept_dt", "rcept_no", "bsns_year"))
        if (not re.fullmatch(r"[0-9]{6}", ticker) or not isinstance(text, str)
                or not isinstance(filed, str) or not re.fullmatch(r"[0-9]{8}", filed)
                or not isinstance(receipt, str) or not re.fullmatch(r"[0-9]{14}", receipt)
                or not isinstance(year, str) or not re.fullmatch(r"[0-9]{4}", year)
                or not isinstance(row.get("report_nm"), str) or not row["report_nm"].strip()):
            raise ValueError(f"invalid overview provenance: {ticker}")
        datetime.strptime(filed, "%Y%m%d")
        usable += 1
        previous = prior_rows.get(ticker, {})
        if (str(previous.get("fiscal_year") or "") > year
                or str(previous.get("filed_at") or "") > filed):
            older += 1
            continue
        name = (listed.get(ticker) or {}).get("name") or row.get("name")
        if not isinstance(name, str) or not name.strip():
            raise ValueError(f"missing overview name: {ticker}")
        excerpt, cut = _cut_at_sentence(text, BIZ_OVERVIEW_PUBLISH_CHARS)
        # The shared cutter can append an ellipsis after the limit. The existing
        # member-map consumer counts that character within its 600-character cap.
        if len(excerpt) > BIZ_OVERVIEW_PUBLISH_CHARS:
            excerpt = excerpt[:BIZ_OVERVIEW_PUBLISH_CHARS - 1] + "…"
        candidate = {
            "name": name, "text": excerpt, "chars": len(excerpt),
            "truncated": bool(row.get("truncated")) or cut,
            "fiscal_year": year, "filed_at": filed, "report": row["report_nm"],
            "source": SOURCE, "url": DART + receipt,
        }
        projected = project_public_business_overviews({PUBLIC_FILE: {
            "_meta": {"generated_at": generated_at, "count": 1}, "rows": {ticker: candidate}}})
        if projected["coverage"]["accepted"] != 1:
            rejected += 1
            continue
        rows[ticker] = candidate
    if not usable:
        raise ValueError("no usable raw overview rows; existing snapshot preserved")
    changed = rows != prior_rows
    payload = prior if not changed else {
        "_meta": {
            "generated_at": generated_at, "source": SOURCE + " (원문 발췌 · LLM 0)",
            "count": len(rows), "universe": len(set(raw_rows) | set(prior_rows)),
            "publish_chars": BIZ_OVERVIEW_PUBLISH_CHARS,
            "truncated_n": sum(bool(row.get("truncated")) for row in rows.values()),
            "note": "로컬 원문 발췌 갱신. 원문 없는 기존 행은 출처 날짜 그대로 보존.",
        },
        "rows": rows,
    }
    return payload, {"raw": len(raw_rows), "usable": usable, "empty": empty,
                     "older_preserved": older, "consumer_rejected": rejected,
                     "public": len(rows), "changed": changed}


def refresh(data_dir, *, check=False):
    data_dir = Path(data_dir)
    output = data_dir / PUBLIC_FILE
    raw = json.loads((data_dir / "dart_business_overview.json").read_text(encoding="utf-8"))
    prior = json.loads(output.read_text(encoding="utf-8")) if output.exists() else {"rows": {}}
    listed = json.loads((data_dir / "kr_listed.json").read_text(encoding="utf-8"))
    payload, summary = build_public(raw, prior, listed)
    if summary["changed"] and not check:
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=data_dir,
                                             prefix=".overview-", delete=False) as handle:
                temporary = Path(handle.name)
                json.dump(payload, handle, ensure_ascii=False)
            os.replace(temporary, output)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
    return {**summary, "written": summary["changed"] and not check}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, default=ROOT / "data")
    parser.add_argument("--check", action="store_true", help="validate locally without writing")
    args = parser.parse_args(argv)
    try:
        print(json.dumps(refresh(args.data_dir, check=args.check), ensure_ascii=False))
        return 0
    except (OSError, ValueError, TypeError, AttributeError) as error:
        print(json.dumps({"error": str(error), "written": False}, ensure_ascii=False))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

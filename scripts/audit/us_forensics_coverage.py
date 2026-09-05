#!/usr/bin/env python3
"""미장 리포트 6개 사실 소스의 종목 커버리지 대장을 만든다.

행 존재와 수집 성공은 같은 뜻이 아니다. 내부자·13D/G·13F·Form 144는
이벤트가 있는 종목만 행을 내보내므로, 행 부재를 데이터 결손으로 단정하지 않는다.
처리 성공 대장이 있는 소스만 processed N/M을 별도로 신고한다.
"""
from __future__ import annotations

import argparse
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "data"
DEFAULT_OUTPUT = DATA / "metadata" / "us_forensics_coverage.json"

SOURCES = {
    "insider": {
        "artifact": "us_insider_trades.json",
        "meaning": "SEC Form 4 내부자 실제 거래 이벤트 보유 종목",
        "absence": "해당 기간 이벤트 없음 또는 현재 스냅샷 미포함",
    },
    "holdings": {
        "artifact": "us_major_holdings.json",
        "meaning": "SEC 13D/G 5% 이상 대량보유 이벤트 보유 종목",
        "absence": "해당 기간 이벤트 없음 또는 현재 스냅샷 미포함",
    },
    "smart_money": {
        "artifact": "us_smart_money_13f.json",
        "meaning": "추적 중인 13F 운용사 포트폴리오 편입 종목",
        "absence": "추적 운용사 보유 목록에 없음; 전체 기관 보유 부재 뜻이 아님",
    },
    "short_interest": {
        "artifact": "us_short_interest.json",
        "meaning": "거래소 공매도 잔고 값 보유 종목",
        "absence": "현재 공매도 스냅샷에 값 없음",
    },
    "disclosure_forensics": {
        "artifact": "us_disclosure_forensics.json",
        "meaning": "SEC 8-K 수집 상태와 최근 이벤트를 함께 보유한 종목",
        "absence": "통합 산출물에 행이 없음",
    },
    "form144": {
        "artifact": "us_form144.json",
        "meaning": "SEC Form 144 매도 예정 신고 이벤트 보유 종목",
        "absence": "해당 기간 이벤트 없음 또는 현재 스냅샷 미포함",
    },
}


def _load(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def _tickers(doc: dict[str, Any]) -> set[str]:
    return {
        str(row.get("ticker") or "").strip().upper()
        for row in doc.get("stocks") or []
        if str(row.get("ticker") or "").strip()
    }


def _age_hours(generated_at: str, now: datetime) -> float | None:
    if not generated_at:
        return None
    try:
        stamp = datetime.fromisoformat(generated_at.replace("Z", "+00:00"))
        if stamp.tzinfo is None:
            stamp = stamp.replace(tzinfo=timezone.utc)
        return round(max(0.0, (now - stamp.astimezone(timezone.utc)).total_seconds() / 3600), 2)
    except ValueError:
        return None


def build_report(now: datetime | None = None) -> dict[str, Any]:
    now = now or datetime.now(timezone.utc)
    universe_doc = _load(DATA / "us_universe_combined.json")
    universe = {
        str(ticker).strip().upper()
        for ticker in universe_doc.get("tickers") or []
        if str(ticker).strip()
    }
    if not universe:
        raise ValueError("US universe is empty")

    source_rows: dict[str, dict[str, Any]] = {}
    present_sets: dict[str, set[str]] = {}
    for key, spec in SOURCES.items():
        doc = _load(DATA / spec["artifact"])
        meta = doc.get("_meta") or {}
        present = _tickers(doc) & universe
        absent = sorted(universe - present)
        generated_at = str(meta.get("generated_at") or "")
        row: dict[str, Any] = {
            "artifact": spec["artifact"],
            "meaning": spec["meaning"],
            "absence_means": spec["absence"],
            "generated_at": generated_at or None,
            "age_hours_at_audit": _age_hours(generated_at, now),
            "record_present_n": len(present),
            "record_denominator_n": len(universe),
            "record_absent_n": len(absent),
            "record_absent_tickers": absent,
        }

        if key == "disclosure_forensics":
            processed_n = int(meta.get("processed_n") or 0)
            unresolved = sorted(
                str(ticker).upper()
                for ticker in meta.get("unprocessed_tickers") or []
                if str(ticker).upper() in universe
            )
            row.update({
                "processed_n": processed_n,
                "processed_denominator_n": len(universe),
                "unprocessed_n": len(unresolved),
                "unprocessed_tickers": unresolved,
                "event_present_n": int(meta.get("event_present_n") or 0),
                "no_recent_event_n": int(meta.get("no_recent_8k_n") or 0),
            })
        elif key == "short_interest":
            row.update({
                "processed_n": int(meta.get("covered_n") or 0),
                "processed_denominator_n": int(meta.get("universe_n") or len(universe)),
                "unprocessed_tickers": absent,
            })
        else:
            row.update({
                "processed_n": None,
                "processed_denominator_n": len(universe),
                "unprocessed_tickers": None,
                "processing_note": "산출물에 성공 티커 대장이 없어 이벤트 부재와 미수집을 분리할 수 없음",
            })

        source_rows[key] = row
        present_sets[key] = present

    all_six = set.intersection(*present_sets.values()) if present_sets else set()
    return {
        "_meta": {
            "generated_at": now.isoformat(),
            "universe_source": "data/us_universe_combined.json",
            "universe_n": len(universe),
            "source_n": len(SOURCES),
            "definition": "record_present는 해당 소스 행 존재, processed는 원천 조회 성공 대장이 있는 경우만 표시",
        },
        "sources": source_rows,
        "intersection": {
            "all_six_record_present_n": len(all_six),
            "all_six_record_denominator_n": len(universe),
            "all_six_record_present_tickers": sorted(all_six),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", default=str(DEFAULT_OUTPUT))
    args = parser.parse_args()
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    report = build_report()
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    meta = report["_meta"]
    print(f"[us_forensics_coverage] sources {meta['source_n']}/6 | universe {meta['universe_n']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

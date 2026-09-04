#!/usr/bin/env python3
"""검증된 staging exec_paper 요약만 operator portfolio로 승격한다.

Quick 분석은 실제 데이터와 AI 비용 차단을 분리하기 위해 VERITY_MODE=staging으로
실행된다. 따라서 main.py의 최신 결과는 portfolio.dev.json에 저장된다. 알파콘솔은
private Supabase의 portfolio_full.json을 읽으므로, 전체 staging 포트폴리오를 섞지 않고
exec_paper 한 필드만 상태 원장과 대조한 뒤 data/portfolio.json에 원자적으로 반영한다.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = ROOT / "data" / "portfolio.dev.json"
DEFAULT_DESTINATION = ROOT / "data" / "portfolio.json"
DEFAULT_STATE = ROOT / "data" / "exec_paper_state.json"


class PromotionError(RuntimeError):
    """승격 계약 불일치."""


def _read_object(path: Path, label: str) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PromotionError(f"{label} read failed: {type(exc).__name__}") from exc
    if not isinstance(value, dict):
        raise PromotionError(f"{label} must be a JSON object")
    return value


def _validate(summary: dict[str, Any], state: dict[str, Any]) -> None:
    if summary.get("capital_mode") != "paper_only" or summary.get("real_orders") != 0:
        raise PromotionError("exec_paper is not paper-only with zero real orders")

    try:
        datetime.fromisoformat(str(summary["as_of"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise PromotionError("exec_paper.as_of is missing or invalid") from exc

    expected = {
        "version": state.get("version"),
        "formula_version": state.get("formula_version"),
        "cash": round(float(state.get("cash") or 0)),
        "pending": len(state.get("pending") or []),
        "trades_total": int(state.get("trades") or 0),
        "market_sessions": int(state.get("market_sessions") or 0),
        "price_snapshot": state.get("price_snapshot") or {},
        "denominator": state.get("last_denominator") or {},
        "target_holdings": len(state.get("target_tickers") or []),
    }
    actual = {key: summary.get(key) for key in expected}
    mismatches = [key for key in expected if actual[key] != expected[key]]

    state_positions = sorted(str(key) for key in (state.get("positions") or {}))
    summary_positions = sorted(str(key) for key in (summary.get("positions") or {}))
    if summary_positions != state_positions:
        mismatches.append("positions")

    state_targets = [str(key) for key in (state.get("target_tickers") or [])]
    summary_targets = [str(row.get("ticker") or "") for row in (summary.get("targets") or [])]
    if summary_targets != state_targets:
        mismatches.append("targets")

    state_flags = set(state.get("last_flags") or [])
    summary_flags = set(summary.get("flags") or [])
    if not state_flags.issubset(summary_flags):
        mismatches.append("flags")

    if mismatches:
        raise PromotionError("state mismatch: " + ",".join(sorted(set(mismatches))))


def _atomic_write(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = path.stat().st_mode & 0o777 if path.exists() else 0o644
    fd, temp_name = tempfile.mkstemp(prefix=".portfolio-paper-", suffix=".json", dir=path.parent)
    try:
        os.chmod(temp_name, mode)
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(value, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_name, path)
    finally:
        if os.path.exists(temp_name):
            os.unlink(temp_name)


def promote_exec_paper(source: Path, destination: Path, state_path: Path) -> dict[str, Any]:
    staging = _read_object(source, "staging portfolio")
    production = _read_object(destination, "operator portfolio")
    state = _read_object(state_path, "paper state")
    summary = staging.get("exec_paper")
    if not isinstance(summary, dict):
        raise PromotionError("staging portfolio has no exec_paper object")

    _validate(summary, state)
    production["exec_paper"] = summary
    _atomic_write(destination, production)
    return summary


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--destination", type=Path, default=DEFAULT_DESTINATION)
    parser.add_argument("--state", type=Path, default=DEFAULT_STATE)
    args = parser.parse_args()

    try:
        summary = promote_exec_paper(args.source, args.destination, args.state)
    except PromotionError as exc:
        print(f"[exec_paper_promote] FAIL: {exc}", file=sys.stderr)
        return 1

    print(
        "[exec_paper_promote] "
        f"version={summary.get('version')} sessions={summary.get('market_sessions')} "
        f"pending={summary.get('pending')} trades={summary.get('trades_total')}"
    )
    print("exec paper promote: 1/1")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

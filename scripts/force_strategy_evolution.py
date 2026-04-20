"""
수동 trigger: Brain V2 전략 진화 강제 실행.

사용:
  python3 scripts/force_strategy_evolution.py [--dry-run]

일반 파이프라인과 무관하게 현재 portfolio.json + 스냅샷 데이터로
Claude 에게 가중치 조정 제안 요청. 최소 스냅샷 기준이 5일 (forced) 로
완화됨 — 단 MAX_WEIGHT_DELTA ±0.05 / MAX_CUMULATIVE_DRIFT 0.20 안전장치는
그대로 작동.

--dry-run: Claude 제안만 받고 constitution 저장 안 함 (검토용).
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from api.intelligence.strategy_evolver import run_evolution_cycle  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="strategy_evolver 수동 발화")
    ap.add_argument("--dry-run", action="store_true",
                    help="Claude 제안만 받고 constitution 실제 변경 안 함")
    args = ap.parse_args()

    portfolio_path = ROOT / "data" / "portfolio.json"
    if not portfolio_path.exists():
        print(f"ERROR: {portfolio_path} 없음")
        return 1

    portfolio = json.loads(portfolio_path.read_text(encoding="utf-8"))
    print(f"portfolio 로드 완료 (updated_at: {portfolio.get('updated_at', '?')})")
    print()

    if args.dry_run:
        # dry-run: 원본 constitution 을 stash 한 뒤 실행, 복원
        const_path = ROOT / "data" / "verity_constitution.json"
        original = const_path.read_text(encoding="utf-8")
        try:
            result = run_evolution_cycle(portfolio, force=True)
        finally:
            const_path.write_text(original, encoding="utf-8")
            print()
            print("(dry-run: constitution.json 복원됨)")
    else:
        result = run_evolution_cycle(portfolio, force=True)

    print()
    print("── 결과 ──")
    print(f"  status: {result.get('status')}")
    print(f"  forced: {result.get('forced')}")
    print(f"  reason: {result.get('reason', '')[:200]}")
    if result.get("new_version"):
        print(f"  new_version: {result['new_version']}")
    if result.get("changes"):
        changes = result["changes"]
        fw = changes.get("fact_score_weights", {})
        sw = changes.get("sentiment_score_weights", {})
        if fw:
            print(f"  fact_score_weights 변경 ({len(fw)}개):")
            for k, v in list(fw.items())[:8]:
                print(f"    {k}: {v:+.4f}")
        if sw:
            print(f"  sentiment_score_weights 변경 ({len(sw)}개):")
            for k, v in list(sw.items())[:8]:
                print(f"    {k}: {v:+.4f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

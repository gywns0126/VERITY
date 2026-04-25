#!/usr/bin/env python3
"""
Verity Brain 시스템 품질 + KB 사용 패턴 한방 분석.

PR #12 / #13 이 누적해온 데이터를 한 명령으로 보기 좋게 출력. 2~4주 데이터
누적 후 충돌 룰 도입 결정에 활용.

사용:
  python3 scripts/analyze_brain.py                # 기본 — 텍스트 리포트
  python3 scripts/analyze_brain.py --json         # 원시 집계 JSON
  python3 scripts/analyze_brain.py --top 20       # 상위 N 개
  python3 scripts/analyze_brain.py --conflicts    # 충돌 후보 페어만
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

# 잠재 충돌 페어 — 투자 철학 측면. 같이 나오면 Gemini 에 모순 신호.
CONFLICT_PAIRS = [
    ("graham_intelligent_investor", "oneil_canslim",
     "안전마진 매수 ↔ 신고가 돌파 매수"),
    ("graham_intelligent_investor", "covel_turtle_trader",
     "내재가치 ↔ 가격만 추종"),
    ("buffett_essays", "nison_candlestick_psychology",
     "장기 holding ↔ 단기 캔들 반전"),
    ("buffett_essays", "carter_mastering_trade",
     "장기 가치 ↔ TTM Squeeze 단기"),
    ("bogle_common_sense", "livermore_operator",
     "패시브 인덱스 ↔ 피봇 타이밍"),
    ("bogle_common_sense", "antonacci_dual_momentum",
     "타이밍 무용 ↔ 모멘텀 자산배분"),
    ("malkiel_random_walk", "murphy_technical_analysis",
     "EMH ↔ 차트 분석"),
    ("malkiel_random_walk", "oneil_canslim",
     "EMH ↔ CANSLIM 적극 종목 선정"),
    ("douglas_trading_in_zone", "lefevre_reminiscences",
     "감정 무시 시스템 ↔ 본능적 추세 추종"),
    ("aronson_evidence_based", "nison_candlestick_psychology",
     "통계적 유의성만 ↔ 주관 캔들 패턴"),
]


def _load_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _format_brain_quality(bq: dict) -> str:
    if not bq:
        return "  (brain_quality 데이터 없음 — Full cron 1회 이상 실행 필요)"
    status = bq.get("status", "?")
    score = bq.get("score")
    period = bq.get("period", "?")
    if status == "insufficient_data":
        note = bq.get("note", "")
        return f"  점수: 미산출 (사유: {note}) · 기간 {period}"
    if status == "no_data":
        return f"  점수: 미산출 (등급별 표본 없음) · 기간 {period}"
    comps = bq.get("components", {}) or {}
    metrics = bq.get("metrics", {}) or {}
    lines = [
        f"  점수: {score:.1f}/100  · 상태 {status} · 기간 {period}",
        f"    구성:  양성 적중률 {comps.get('positive_hit_rate_score',0):.1f}/40  "
        f"+ AVOID 회피 {comps.get('avoid_avoidance_score',0):.1f}/30  "
        f"+ 등급 분리도 {comps.get('grade_separation_score',0):.1f}/30",
        f"    표본:  총 {metrics.get('total_samples',0)}건  "
        f"(STRONG_BUY {metrics.get('strong_buy_n',0)} · BUY {metrics.get('buy_n',0)} · AVOID {metrics.get('avoid_n',0)})",
        f"    분리:  STRONG_BUY avg − AVOID avg = "
        f"{metrics.get('grade_spread_pp','—')}%p  ·  양성 가중 hit_rate {metrics.get('weighted_positive_hit_rate','—')}%",
    ]
    return "\n".join(lines)


def _format_books(usage: dict, top_n: int) -> list:
    books = usage.get("books") or {}
    total = usage.get("total_calls", 0) or 0
    if not books or total == 0:
        return ["  (인용 통계 없음 — Full cron 1회 이상 실행 필요)"]
    sorted_books = sorted(books.items(), key=lambda x: -x[1])[:top_n]
    width = max((len(b) for b, _ in sorted_books), default=20)
    out = [f"  총 인용 호출 {total}건"]
    for book_id, n in sorted_books:
        pct = n / total * 100
        bar = "█" * max(1, int(pct / 2))
        out.append(f"    {book_id:<{width}}  {n:>4}회  {pct:>5.1f}%  {bar}")
    return out


def _format_combinations(usage: dict, top_n: int) -> list:
    combos = usage.get("combinations") or {}
    total = usage.get("total_calls", 0) or 0
    if not combos:
        return ["  (조합 통계 없음)"]
    sorted_combos = sorted(combos.items(), key=lambda x: -x[1])[:top_n]
    out = []
    for combo_key, n in sorted_combos:
        pct = n / total * 100 if total else 0
        books_in_combo = combo_key.split("+")
        out.append(f"    {n:>4}회 ({pct:>5.1f}%)  {' + '.join(books_in_combo)}")
    return out


def _format_triggers(usage: dict, top_n: int) -> list:
    triggers = usage.get("triggers") or {}
    if not triggers:
        return ["  (트리거 통계 없음)"]
    sorted_t = sorted(triggers.items(), key=lambda x: -x[1])[:top_n]
    out = []
    for tk, n in sorted_t:
        out.append(f"    {n:>4}회  {tk}")
    return out


def _detect_conflicts(usage: dict) -> list:
    """combinations 카운터에서 사전 정의된 CONFLICT_PAIRS 가 얼마나 자주 나오는지."""
    combos = usage.get("combinations") or {}
    findings = []
    for a, b, desc in CONFLICT_PAIRS:
        # combo key 는 sorted 라 같은 순서 보장
        key1 = "+".join(sorted([a, b]))
        # 정확 매칭 + 3권 조합 등 superset 까지 모두
        exact = combos.get(key1, 0)
        superset_total = 0
        for ckey, cnt in combos.items():
            parts = ckey.split("+")
            if a in parts and b in parts and ckey != key1:
                superset_total += cnt
        total = exact + superset_total
        if total > 0:
            findings.append((total, exact, superset_total, a, b, desc))
    findings.sort(reverse=True)
    return findings


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Verity Brain 시스템 품질 + KB 인용 패턴 분석"
    )
    ap.add_argument("--data-dir", default=None,
                    help="data/ 경로 (기본: repo root /data)")
    ap.add_argument("--top", type=int, default=10,
                    help="상위 N 개 (default 10)")
    ap.add_argument("--json", action="store_true",
                    help="원시 집계 JSON 으로 출력")
    ap.add_argument("--conflicts", action="store_true",
                    help="충돌 후보 페어만 출력")
    args = ap.parse_args()

    repo_root = Path(__file__).resolve().parent.parent
    data_dir = Path(args.data_dir) if args.data_dir else (repo_root / "data")

    portfolio = _load_json(data_dir / "portfolio.json")
    usage = _load_json(data_dir / "brain_kb_usage.json")
    brain_quality = portfolio.get("brain_quality") or {}
    brain_accuracy = portfolio.get("brain_accuracy") or {}

    if args.json:
        out = {
            "brain_quality": brain_quality,
            "brain_accuracy_summary": {
                "insight": brain_accuracy.get("insight", ""),
                "grades": brain_accuracy.get("grades", {}),
            },
            "kb_usage_total_calls": usage.get("total_calls", 0),
            "top_books": dict(sorted((usage.get("books") or {}).items(),
                                     key=lambda x: -x[1])[:args.top]),
            "top_combinations": dict(sorted((usage.get("combinations") or {}).items(),
                                            key=lambda x: -x[1])[:args.top]),
            "top_triggers": dict(sorted((usage.get("triggers") or {}).items(),
                                        key=lambda x: -x[1])[:args.top]),
            "conflict_findings": [
                {"total": t, "exact_pair": e, "superset": s,
                 "books": [a, b], "desc": d}
                for t, e, s, a, b, d in _detect_conflicts(usage)
            ],
        }
        print(json.dumps(out, ensure_ascii=False, indent=2))
        return 0

    if args.conflicts:
        print("📌 충돌 가능 책 페어 — 누적 동시 인용 빈도")
        print("─" * 70)
        findings = _detect_conflicts(usage)
        if not findings:
            print("  (아직 누적 데이터 부족 — Full cron 며칠 더 돌아야)")
            return 0
        for total, exact, superset, a, b, desc in findings:
            print(f"  {total:>4}회 (정확 {exact}, 3권+ 조합 {superset})")
            print(f"        {a}  ↔  {b}")
            print(f"        ⚠ {desc}")
        return 0

    # 기본 — 사람이 보기 좋은 텍스트 리포트
    print("=" * 70)
    print("VERITY BRAIN — 시스템 품질 + KB 인용 분석")
    print(f"  data dir: {data_dir}")
    print("=" * 70)
    print()
    print("📊 brain_quality (PR #12)")
    print(_format_brain_quality(brain_quality))
    print()
    print("💬 brain_accuracy.insight")
    print(f"  {brain_accuracy.get('insight') or '(없음)'}")
    print()
    print(f"📚 KB 책별 인용 횟수 TOP {args.top} (PR #13)")
    for line in _format_books(usage, args.top):
        print(line)
    print()
    print(f"🔗 책 조합 (combinations) TOP {args.top}")
    for line in _format_combinations(usage, args.top):
        print(line)
    print()
    print(f"🎯 트리거 (조건) TOP {args.top}")
    for line in _format_triggers(usage, args.top):
        print(line)
    print()
    print("⚠ 충돌 가능 페어 — 동시 인용 빈도 (예방 분석)")
    findings = _detect_conflicts(usage)
    if not findings:
        print("  (충돌 데이터 부족 — 며칠 더 누적 필요)")
    else:
        for total, exact, superset, a, b, desc in findings[:5]:
            short_a = a.split("_")[0]
            short_b = b.split("_")[0]
            print(f"  {total:>4}회  {short_a} ↔ {short_b}  · {desc}")

    last_updated = usage.get("last_updated", "(없음)")
    print()
    print(f"마지막 갱신: {last_updated}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

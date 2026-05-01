"""ATR 마이그레이션 14일 분석 + 자동 판정 — Phase 0 P-06 후속.

사용법:
    python scripts/analyze_atr_migration.py
    python scripts/analyze_atr_migration.py --window-start 2026-05-03 --window-end 2026-05-16

판정 매트릭스 (사전 결정 2026-05-01):
    avg_diff_pct < 15%  → ok
    15% ~ 20%           → monitoring
    > 20%               → fail (단 market_abnormal 시 monitoring_escape)

market_abnormal escape 조건 (윈도우 내 한 번이라도):
    VIX > 30 OR |KOSPI daily change_pct| > 5 OR |KOSDAQ| > 5

출력:
    {
      verdict: "ok" | "monitoring" | "fail" | "monitoring_escape",
      avg_diff_pct, p95_diff_pct, max_diff_pct,
      outlier_count, sample_count,
      market_abnormal, abnormal_signals,
      recommendation: ...
    }
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from statistics import mean
from typing import Optional


# 판정 임계 (Phase 0 사전 결정 2026-05-01)
THRESHOLD_OK = 15.0
THRESHOLD_MONITORING = 20.0  # 15~20% monitoring, 이상 fail
OUTLIER_DIFF_PCT = 30.0

# market_abnormal 임계
ABNORMAL_VIX = 30.0
ABNORMAL_INDEX_CHANGE_PCT = 5.0


def load_migration_log(log_path: Path, window_start: Optional[str], window_end: Optional[str]) -> list[dict]:
    """atr_migration_log.jsonl + archive/*.jsonl.gz 모두 합쳐서 윈도우 필터."""
    rows: list[dict] = []
    if log_path.exists():
        for line in log_path.read_text().splitlines():
            try:
                rows.append(json.loads(line))
            except Exception:
                continue

    # archive 도 포함
    archive_dir = log_path.parent / "archive"
    if archive_dir.exists():
        import gzip
        for archive in sorted(archive_dir.glob("atr_migration_log_*.jsonl.gz")):
            try:
                with gzip.open(archive, "rt") as f:
                    for line in f:
                        try:
                            rows.append(json.loads(line))
                        except Exception:
                            continue
            except Exception:
                continue

    if window_start or window_end:
        filtered = []
        for r in rows:
            ts = r.get("timestamp", "")[:10]
            if window_start and ts < window_start:
                continue
            if window_end and ts > window_end:
                continue
            filtered.append(r)
        return filtered
    return rows


def compute_metrics(rows: list[dict]) -> dict:
    """diff_pct 분포 통계."""
    diffs = [abs(r.get("diff_pct", 0)) for r in rows if "diff_pct" in r]
    if not diffs:
        return {
            "sample_count": 0,
            "avg_diff_pct": None,
            "p95_diff_pct": None,
            "max_diff_pct": None,
            "outlier_count": 0,
        }
    diffs_sorted = sorted(diffs)
    p95_idx = int(len(diffs_sorted) * 0.95) if len(diffs_sorted) > 1 else 0
    return {
        "sample_count": len(diffs),
        "avg_diff_pct": round(mean(diffs), 2),
        "p95_diff_pct": round(diffs_sorted[p95_idx], 2),
        "max_diff_pct": round(diffs_sorted[-1], 2),
        "outlier_count": sum(1 for d in diffs if d > OUTLIER_DIFF_PCT),
    }


def detect_market_abnormal(
    history_dir: Path,
    window_start: Optional[str],
    window_end: Optional[str],
) -> tuple[bool, list[dict]]:
    """history snapshot 의 macro/market_summary 검사. 윈도우 내 1번이라도 abnormal 이면 True.

    Returns: (is_abnormal, [signals]) — signals 는 abnormal 일자 + 사유 리스트.
    """
    if not history_dir.exists():
        return False, []

    signals: list[dict] = []
    for snapshot_file in sorted(history_dir.glob("*.json")):
        date_str = snapshot_file.stem
        if window_start and date_str < window_start:
            continue
        if window_end and date_str > window_end:
            continue
        try:
            j = json.loads(snapshot_file.read_text())
        except Exception:
            continue

        vix = (j.get("macro") or {}).get("vix") or {}
        vix_val = vix.get("value")
        kospi = (j.get("market_summary") or {}).get("kospi") or {}
        kosdaq = (j.get("market_summary") or {}).get("kosdaq") or {}

        reasons = []
        if isinstance(vix_val, (int, float)) and vix_val > ABNORMAL_VIX:
            reasons.append(f"vix={vix_val:.1f} > {ABNORMAL_VIX}")
        kospi_chg = kospi.get("change_pct")
        if isinstance(kospi_chg, (int, float)) and abs(kospi_chg) > ABNORMAL_INDEX_CHANGE_PCT:
            reasons.append(f"kospi={kospi_chg:+.2f}% (|chg|>{ABNORMAL_INDEX_CHANGE_PCT})")
        kosdaq_chg = kosdaq.get("change_pct")
        if isinstance(kosdaq_chg, (int, float)) and abs(kosdaq_chg) > ABNORMAL_INDEX_CHANGE_PCT:
            reasons.append(f"kosdaq={kosdaq_chg:+.2f}%")

        if reasons:
            signals.append({"date": date_str, "reasons": reasons})

    return (len(signals) > 0), signals


def decide_verdict(metrics: dict, market_abnormal: bool) -> dict:
    """판정 매트릭스 적용. Returns {verdict, recommendation}."""
    avg = metrics.get("avg_diff_pct")
    if avg is None:
        return {
            "verdict": "insufficient_data",
            "recommendation": "atr_migration_log.jsonl 비어 있음. ATR_MIGRATION_LOGGING=true + 운영 cycle 1회 후 재실행.",
        }

    if avg < THRESHOLD_OK:
        return {
            "verdict": "ok",
            "recommendation": (
                "Wilder vs SMA 평균 차이 정상 범위. ATR_MIGRATION_LOGGING=false 처리 후 "
                "Phase 1.5.1 진행 가능."
            ),
        }

    if avg < THRESHOLD_MONITORING:
        return {
            "verdict": "monitoring",
            "recommendation": (
                f"평균 차이 {avg}% (15~20% 구간). 7일 추가 모니터링. "
                "ATR_MIGRATION_START_DATE 갱신 또는 수동 OFF 후 재판정."
            ),
        }

    # avg >= 20% — fail 후보
    if market_abnormal:
        return {
            "verdict": "monitoring_escape",
            "recommendation": (
                f"평균 차이 {avg}% (20% 초과) 이지만 market_abnormal escape 발동. "
                "시장 비정상 신호로 인한 ATR 분포 왜곡 가능성. "
                "정상 시장 7일 추가 모니터링 후 재판정. 즉시 rollback 보류."
            ),
        }

    return {
        "verdict": "fail",
        "recommendation": (
            f"평균 차이 {avg}% (20% 초과). market_abnormal escape 미발동. "
            "scripts/rollback_atr_to_sma.sh 실행 권고. Phase 0 자체 재검토 필요."
        ),
    }


def analyze(
    log_path: Path = Path("data/metadata/atr_migration_log.jsonl"),
    history_dir: Path = Path("data/history"),
    window_start: Optional[str] = None,
    window_end: Optional[str] = None,
) -> dict:
    """전체 분석 + 판정. Returns full report dict."""
    rows = load_migration_log(log_path, window_start, window_end)
    metrics = compute_metrics(rows)
    market_abnormal, abnormal_signals = detect_market_abnormal(
        history_dir, window_start, window_end
    )
    decision = decide_verdict(metrics, market_abnormal)

    return {
        "window_start": window_start,
        "window_end": window_end,
        "computed_at": datetime.now().isoformat(),
        "metrics": metrics,
        "market_abnormal": market_abnormal,
        "abnormal_signals": abnormal_signals,
        **decision,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", default="data/metadata/atr_migration_log.jsonl")
    ap.add_argument("--history-dir", default="data/history")
    ap.add_argument("--window-start", default=None, help="ISO date (YYYY-MM-DD)")
    ap.add_argument("--window-end", default=None, help="ISO date")
    ap.add_argument("--json", action="store_true", help="JSON output (for piping)")
    args = ap.parse_args()

    report = analyze(
        log_path=Path(args.log),
        history_dir=Path(args.history_dir),
        window_start=args.window_start,
        window_end=args.window_end,
    )

    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return

    m = report["metrics"]
    print(f"=== ATR Migration Analysis ===")
    print(f"window: {report['window_start'] or 'all'} ~ {report['window_end'] or 'all'}")
    print(f"sample_count: {m['sample_count']}")
    print(f"avg_diff_pct: {m['avg_diff_pct']}")
    print(f"p95_diff_pct: {m['p95_diff_pct']}")
    print(f"max_diff_pct: {m['max_diff_pct']}")
    print(f"outlier_count (>30%): {m['outlier_count']}")
    print(f"market_abnormal: {report['market_abnormal']}")
    if report['abnormal_signals']:
        print(f"  signals ({len(report['abnormal_signals'])}):")
        for s in report['abnormal_signals'][:5]:
            print(f"    {s['date']}: {', '.join(s['reasons'])}")
    print(f"\n=== VERDICT: {report['verdict'].upper()} ===")
    print(f"\n{report['recommendation']}")

    # exit code: 0 ok / 1 monitoring / 2 fail / 3 escape / 4 insufficient
    code_map = {
        "ok": 0, "monitoring": 1, "fail": 2,
        "monitoring_escape": 3, "insufficient_data": 4,
    }
    sys.exit(code_map.get(report["verdict"], 1))


if __name__ == "__main__":
    main()

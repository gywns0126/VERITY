"""
slippage_monitor — 실측 슬리피지 vs VAMS 가정 비교 리포트.

배경:
  VAMS 본체는 Almgren-Chriss sqrt 모델로 시장충격 슬리피지를 계산하며, 프로필별
  impact_coeff_bps (대개 30bp) 를 계수로 쓴다. 실측치가 이 가정에서 크게 벗어나면
  전체 수익률이 편향되므로 월 1회 체크하는 것이 목적.

입력:
  data/history.json             (VAMS 가상매매)
  data/auto_trade_history.json  (실거래, 존재 시)

각 엔트리에 slippage_bps 필드가 있어야 집계 대상. (engine.py execute_buy/execute_sell
가 자동 기록. 과거 엔트리는 누락일 수 있음 → 자동 skip.)

출력:
  - 전체 평균/중앙값/P95 슬리피지
  - 매수/매도 분리 평균
  - asset_class 별 분리 (KR_STOCK, KR_ETF, US_STOCK, US_ETF)
  - 최근 30일/90일/전체 구간 비교
  - 가정(30bp) 대비 편차 경고

사용:
  python3 scripts/slippage_monitor.py
  python3 scripts/slippage_monitor.py --assumption 30 --window 30
"""
import argparse
import json
import os
import statistics
import sys
from collections import defaultdict
from datetime import datetime, timedelta

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_HERE, ".."))

from api.config import DATA_DIR  # noqa: E402


_VAMS_HISTORY = os.path.join(DATA_DIR, "history.json")
_AUTO_HISTORY = os.path.join(DATA_DIR, "auto_trade_history.json")


def _load(path: str) -> list:
    if not os.path.exists(path):
        return []
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, list) else []
    except Exception as e:
        print(f"[warn] {path} 로드 실패: {e}", file=sys.stderr)
        return []


def _parse_date(s) -> "datetime | None":
    if not s:
        return None
    s = str(s)[:10]
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except ValueError:
        return None


def _quantile(values, q: float) -> float:
    if not values:
        return 0.0
    s = sorted(values)
    idx = max(0, min(len(s) - 1, int(round(q * (len(s) - 1)))))
    return s[idx]


def _summary(values: list) -> dict:
    if not values:
        return {"n": 0}
    return {
        "n": len(values),
        "mean": round(statistics.mean(values), 2),
        "median": round(statistics.median(values), 2),
        "p95": round(_quantile(values, 0.95), 2),
        "max": round(max(values), 2),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="실측 슬리피지 리포트")
    ap.add_argument("--assumption", type=float, default=30.0,
                    help="VAMS 가정 계수 bp (기본 30)")
    ap.add_argument("--window", type=int, default=90,
                    help="최근 N일 윈도우 (기본 90)")
    args = ap.parse_args()

    vams_hist = _load(_VAMS_HISTORY)
    auto_hist = _load(_AUTO_HISTORY)

    entries = []
    for src_name, src in (("vams", vams_hist), ("auto", auto_hist)):
        for e in src:
            if not isinstance(e, dict):
                continue
            bps = e.get("slippage_bps")
            if bps is None:
                continue
            entries.append({
                "source": src_name,
                "date": _parse_date(e.get("date")),
                "side": e.get("side") or e.get("type"),
                "asset_class": e.get("asset_class"),
                "bps": float(bps),
            })

    print(f"총 엔트리: vams={len(vams_hist)}건 / auto={len(auto_hist)}건")
    print(f"slippage_bps 포함: {len(entries)}건")
    if not entries:
        print()
        print("데이터 부족 — VAMS 사이클이 몇 회 돌면 slippage_bps 필드가 자동 누적됩니다.")
        print("권장: 최소 20건 이상 쌓인 뒤 재실행.")
        return 0

    # 전체 분포
    all_bps = [e["bps"] for e in entries]
    print()
    print("=== 전체 분포 ===")
    for k, v in _summary(all_bps).items():
        print(f"  {k:8s} {v}")

    # 최근 N일 윈도우
    cutoff = datetime.now() - timedelta(days=args.window)
    recent = [e["bps"] for e in entries if e["date"] and e["date"] >= cutoff]
    print()
    print(f"=== 최근 {args.window}일 ===")
    for k, v in _summary(recent).items():
        print(f"  {k:8s} {v}")

    # side 분리
    by_side = defaultdict(list)
    for e in entries:
        side = (e["side"] or "UNKNOWN").upper()
        by_side[side].append(e["bps"])
    print()
    print("=== 매수/매도 분리 ===")
    for side in sorted(by_side):
        s = _summary(by_side[side])
        print(f"  {side:6s} n={s['n']:4d}  mean={s.get('mean', 0):.1f}bp  p95={s.get('p95', 0):.1f}bp")

    # asset_class 분리
    by_class = defaultdict(list)
    for e in entries:
        ac = e["asset_class"] or "UNKNOWN"
        by_class[ac].append(e["bps"])
    print()
    print("=== asset_class 분리 ===")
    for ac in sorted(by_class):
        s = _summary(by_class[ac])
        print(f"  {ac:10s} n={s['n']:4d}  mean={s.get('mean', 0):.1f}bp  p95={s.get('p95', 0):.1f}bp")

    # source 분리 (VAMS 가상 vs 실거래)
    by_source = defaultdict(list)
    for e in entries:
        by_source[e["source"]].append(e["bps"])
    print()
    print("=== source 분리 (가상 vs 실거래) ===")
    for src in sorted(by_source):
        s = _summary(by_source[src])
        label = "VAMS 가상" if src == "vams" else "실거래"
        print(f"  {label:10s} n={s['n']:4d}  mean={s.get('mean', 0):.1f}bp  p95={s.get('p95', 0):.1f}bp")

    # 가정 대비 편차 평가
    mean_all = statistics.mean(all_bps)
    dev_pct = ((mean_all - args.assumption) / args.assumption * 100) if args.assumption else 0
    print()
    print(f"=== 가정(impact_coeff_bps={args.assumption}) 대비 편차 ===")
    print(f"  실측 평균 {mean_all:.1f}bp vs 가정 {args.assumption}bp → {dev_pct:+.1f}%")
    if abs(dev_pct) > 50:
        print("  ⚠️  편차 50% 초과 — VAMS 프로필 impact_coeff_bps 튜닝 권장")
    elif abs(dev_pct) > 25:
        print("  🟡 편차 25% 초과 — 샘플 누적 후 재평가")
    else:
        print("  ✅ 가정 범위 내")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""학술 전용 미장 장기 재무 수집 — out-of-sample 검정을 열기 위한 것.

## 왜 (PM 결정 2026-08-18)

텐배거 연구(`docs/TENBAGGER_RESEARCH_KR_2026_08_18.md`)가 KR 단일 구간을 못 벗어났다.
미국으로 out-of-sample 을 치려 했으나 재무가 5년치뿐이라 막혔는데, 🚨 원인을 파보니
**SEC 한계가 아니라 우리 기본값**이었다 —

    api/intelligence/us_financials.py:763
    def build_ticker_snapshot(..., history_quarters: int = 8, history_years: int = 5)

SEC 원천은 훨씬 길다 (KO companyfacts 실호출: NetIncomeLoss 233건 **2007-12-31**~,
StockholdersEquity 147건 2008-12-31~, us-gaap 태그 724개).

## 🚨 운영 경로를 건드리지 않는다

PM 지시 = **"학술 목적으로만 오버 수집하고 1500개 제한은 유지"**.

  · `history_years` **기본값을 바꾸지 않는다** — 바꾸면 운영 산출물
    (`data/us_financials/`, 발행 파이프라인 3곳 종속)이 통째로 커진다.
  · 유니버스도 **sp1500 유지** — 종목 확대는 다른 목적(미장 커버리지 트랙)이고
    이 검정에 필요한 축이 아니다. 섞으면 "왜 12배가 필요한가" 를 설명 못 한다.
  · 산출은 **별도 디렉토리 + gitignore**. 학술 재현용이지 발행물이 아니다.

실측 투영 (2026-08-18):
    현재 sp1500 × 5년      0.09GB
    이력만 해제 × 20년     0.32GB  ← 이것
    둘 다 해제             1.15GB  (repo pack 1.14GB 대비 2배 — 채택 안 함)

## 사용

    python3 scripts/research/collect_us_deep_history.py --limit 50     # 시험
    python3 scripts/research/collect_us_deep_history.py                # 전량

SEC 예의 규정 = 10 req/s 이하, User-Agent 에 연락처. 여기서는 0.15s 간격(≈6.7/s).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO))

from api.intelligence import us_financials as usf  # noqa: E402

# 🚨 학술 전용 산출. 운영 `data/us_financials/` 와 물리 분리한다.
OUT_DIR = REPO / "data" / "research" / "us_financials_deep"
SRC_DIR = REPO / "data" / "us_financials"

HISTORY_YEARS = 20        # SEC 실측 2007~ → 20년이면 전량
HISTORY_QUARTERS = 80     # 20년치 분기
SLEEP = 0.15              # SEC rate limit 준수


def tickers_and_ciks() -> list[tuple[str, int]]:
    """운영 산출물에서 (ticker, cik) 를 읽는다 — 유니버스를 새로 정의하지 않는다.

    🚨 sp1500 제한 유지의 구현이 이것이다. 별도 유니버스를 만들면 제한이 풀린다.
    """
    out = []
    for p in sorted(SRC_DIR.glob("*.json")):
        try:
            d = json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        cik = (d.get("meta") or {}).get("cik")
        t = d.get("ticker") or p.stem
        if isinstance(cik, int):
            out.append((t, cik))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="상위 N 종목만 (시험용)")
    ap.add_argument("--force", action="store_true", help="기존 산출 덮어쓰기")
    args = ap.parse_args()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    pairs = tickers_and_ciks()
    if args.limit:
        pairs = pairs[: args.limit]
    print(f"[deep] 대상 {len(pairs)}종목 · history_years={HISTORY_YEARS} "
          f"(운영 기본값 5 는 불변) · 산출 {OUT_DIR.relative_to(REPO)}", flush=True)

    ok = skip = err = 0
    spans = []
    for i, (t, cik) in enumerate(pairs, 1):
        dst = OUT_DIR / f"{t}.json"
        if dst.exists() and not args.force and dst.stat().st_size > 2000:
            skip += 1
            continue
        try:
            snap = usf.build_ticker_snapshot(
                t, cik, history_quarters=HISTORY_QUARTERS, history_years=HISTORY_YEARS)
        except Exception as e:                       # 개별 실패가 전체를 죽이지 않는다
            err += 1
            print(f"  [{i}/{len(pairs)}] {t} 예외: {str(e)[:90]}", file=sys.stderr)
            time.sleep(SLEEP)
            continue
        if "_error" in snap:
            err += 1
        else:
            dst.write_text(json.dumps(snap, ensure_ascii=False), encoding="utf-8")
            ok += 1
            # 확보된 이력 길이를 표본으로 남긴다 (수집이 실제로 깊어졌는지 자기신고)
            eq = (snap.get("series_annual") or {}).get("stockholders_equity") or []
            ends = [x.get("end") for x in eq if isinstance(x, dict) and x.get("end")]
            if ends:
                spans.append((t, min(ends), len(eq)))
        if i % 100 == 0:
            print(f"  [{i}/{len(pairs)}] ok={ok} skip={skip} err={err}", flush=True)
        time.sleep(SLEEP)

    print(f"[deep] 완료 ok={ok} skip={skip} err={err}")
    if spans:
        spans.sort(key=lambda x: x[1])
        print(f"  최장 이력: {spans[0][0]} {spans[0][1]} ({spans[0][2]}년)")
        mid = spans[len(spans) // 2]
        print(f"  중앙 이력: {mid[0]} {mid[1]} ({mid[2]}년)")
        pre2015 = sum(1 for _, e, _ in spans if e <= "2015-01-01")
        print(f"  🚨 2015 이전 재무 확보 = {pre2015}/{len(spans)} "
              f"({pre2015/len(spans)*100:.0f}%) — out-of-sample 가능 여부")
    return 0


if __name__ == "__main__":
    sys.exit(main())

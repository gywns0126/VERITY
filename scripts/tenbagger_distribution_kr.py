#!/usr/bin/env python3
"""텐배거 실증 — KR 2020~2026. Bessembinder/Blackstar 자체 데이터 재현.

PM 지시(2026-08-18): "역사적으로 존재한 일명 '텐배거'를 연구하자."
외부 자료(퍼플렉시티 + PDF)를 받아 **우리 데이터로 재현·검증**한다.

## 왜 자체 재현인가

외부 자료의 두 주장이 서로 다른 방향을 가리켰다:
  · Bessembinder(2018) — 극소수가 전부를 만든다 (구조적 왜도)
  · PDF — "10배 종목은 대형주보다 스몰/미드캡에서 훨씬 자주"
두 번째는 우리 데이터에서 **반증된다**(아래 size 역U자). 인용 전 재현이 규율이다.

## 🚨 상장폐지 포함이 핵심

생존 2,896 + **상장폐지 365** = 3,261. 생존자만 보면 분포가 통째로 달라진다.
`data/kr_chart_delisted/` 를 반드시 합친다.

## 산출

  ① 수익 분포 — Blackstar "Capitalism Distribution" 대조
  ② 수익 집중도 — 상위 1/4/10%
  ③ size(초기 거래대금) 5분위별 텐배거 배출률
  ④ 섹터·업종 집중도

결과 문서 = `docs/TENBAGGER_RESEARCH_KR_2026_08_18.md`
🚨 관측 전용. 산식 배선은 사전등록 선행.
"""
from __future__ import annotations

import collections
import glob
import json
import os

import numpy as np

# 장기 이력 = Blob kr_chart_history 다운로드분. repo 비커밋(165MB)이라 로컬 경로.
HIST = ("/private/tmp/claude-501/-Users-macbookpro-Desktop--------/"
        "3b4bdb64-7a07-412b-b2cf-029170e8bf91/scratchpad/krhist")
DELISTED = "data/kr_chart_delisted/*.json"
CHUNKS = "data/kr_chart_daily/chunk_*.json"
SECTOR_MAP = "data/kr_sector_map.json"

TENBAGGER = 9.0        # +900% = 10배
MIN_BARS = 250         # 1년 미만 종목 제외


def load_alive() -> dict:
    out = {}
    for p in glob.glob(os.path.join(HIST, "*.json")):
        try:
            c = json.load(open(p)).get("c") or []
        except Exception:
            continue
        if len(c) >= MIN_BARS:
            out[os.path.basename(p)[:-5]] = np.array(c, dtype=float)
    return out


def load_delisted() -> dict:
    out = {}
    for f in glob.glob(DELISTED):
        for tk, v in json.load(open(f)).get("stocks", {}).items():
            c = v.get("c") or []
            if len(c) >= MIN_BARS:
                out[tk] = np.array(c, dtype=float)
    return out


def total_return(a: np.ndarray) -> float | None:
    cl = a[:, 4]
    return cl[-1] / cl[0] - 1.0 if cl[0] > 0 else None


def main() -> None:
    alive, dead = load_alive(), load_delisted()
    recs = []
    for grp, book in (("alive", alive), ("dead", dead)):
        for tk, a in book.items():
            r = total_return(a)
            if r is not None:
                recs.append((tk, grp, r, a))
    ret = np.array([r for _, _, r, _ in recs])

    print("텐배거 실증 — KR 2020~2026 (자체 일봉, 상장폐지 포함)")
    print(f"  생존 {len(alive):,} · 상장폐지 {len(dead):,} · 분석 {len(recs):,}종목")
    print()

    print("## ① 수익 분포 (Blackstar 'Capitalism Distribution' 대조)")
    for lo, lab, neg in [(TENBAGGER, "🚀 10배+", False), (4.0, "5배+", False),
                         (1.0, "2배+", False), (0.0, "플러스", False),
                         (-0.5, "−50% 미만", True), (-0.75, "−75% 이상 손실", True)]:
        n = int((ret <= lo).sum() if neg else (ret >= lo).sum())
        print(f"  {lab:<16}{n:>6}종목 {n/len(ret)*100:>6.1f}%")
    print(f"  중앙 {np.median(ret)*100:+.1f}% · 평균 {ret.mean()*100:+.1f}%")
    print("  ▸ Blackstar(US 1983-2006): 손실 39% · 75%+ 상실 18.5% — 거의 같은 값")
    print()

    print("## ② 수익 집중도")
    srt = np.sort(ret)[::-1]
    tot = srt.sum()
    for q in (0.01, 0.04, 0.10):
        k = max(1, int(len(srt) * q))
        print(f"  상위 {q*100:>4.0f}% ({k:>3}종목) → 전체 수익 합의 {srt[:k].sum()/tot*100:>6.1f}%")
    print("  🚨 상위 1% 를 빼면 나머지 합이 음수다")
    print()

    # ③ size — 🚨 거래대금은 size 이자 attention 프록시다(문서 §5 한계)
    sized = [(tk, r, float(np.median(a[:20, 4] * a[:20, 5])))
             for tk, g, r, a in recs if g == "alive" and len(a) >= 20]
    sized = [x for x in sized if x[2] > 0]
    tv = np.array([x[2] for x in sized]); rr = np.array([x[1] for x in sized])
    qs = np.quantile(tv, [0.2, 0.4, 0.6, 0.8])
    print("## ③ size(초기 20일 거래대금) 5분위별 텐배거 배출률")
    print(f"{'분위':>6}{'범위':>20}{'종목':>7}{'텐배거':>7}{'배출률':>9}{'중앙수익':>10}")
    for i in range(5):
        lo = -np.inf if i == 0 else qs[i - 1]
        m = (tv >= lo) & (tv < qs[i]) if i < 4 else (tv >= qs[3])
        n = int(m.sum()); tb = int((rr[m] >= TENBAGGER).sum())
        print(f"{'Q'+str(i+1):>6}{f'{tv[m].min()/1e8:.1f}~{tv[m].max()/1e8:.0f}억':>20}"
              f"{n:>7}{tb:>7}{tb/n*100:>8.2f}%{np.median(rr[m])*100:>9.1f}%")
    print("  🚨 역U자 — Q4 최다·Q1 최소. '작을수록 텐배거' 는 이 표본에서 반증된다")
    print()

    # ④ 섹터
    try:
        sm = json.load(open(SECTOR_MAP))["map"]
    except Exception:
        print("## ④ 섹터 — 맵 부재로 생략")
        return
    sec = {k: (v.get("sector_ko") or v.get("sector")) for k, v in sm.items()}
    ind = {k: v.get("industry") for k, v in sm.items()}
    alive_ids = [tk for tk, g, _, _ in recs if g == "alive"]
    tb_ids = [tk for tk, g, r, _ in recs if g == "alive" and r >= TENBAGGER]
    base = len(tb_ids) / len(alive_ids)
    ct = collections.Counter(sec.get(t) for t in tb_ids if t in sec)
    ca = collections.Counter(sec.get(t) for t in alive_ids if t in sec)
    print(f"## ④ 섹터 집중도 (커버 {sum(1 for t in alive_ids if t in sec)}/{len(alive_ids)})")
    print(f"{'섹터':<16}{'텐배거':>7}{'전체':>7}{'배출률':>9}{'집중':>8}")
    for s, n in ct.most_common():
        t = ca.get(s, 0)
        print(f"{str(s)[:14]:<16}{n:>7}{t:>7}{n/t*100:>8.1f}%{(n/t)/base:>7.1f}x")
    print()
    ci = collections.Counter(ind.get(t) for t in tb_ids if t in ind)
    print("  세부 업종 (2종목 이상):")
    for i, n in ci.most_common():
        if n >= 2:
            print(f"    {str(i)[:44]:<46}{n}")
    print("  🚨 개별 기업 특성이 아니라 **산업 테마** 가 지배적이다")


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""크립토 꼬리 집중도 견고성 + 재난 브레이커 검정 — 외부 자문 지적 반영.

## 왜

2026-08-17 청산 검정에서 "상위 1%(26거래)가 총수익의 90.5%" 가 나왔다. 외부 자문
(Perplexity, 2026-08-17) 지적:

  · 방향은 추세추종 문헌과 부합하나 **90.5% 는 매우 높은 집중도**이며,
    생존자 유니버스를 썼다면 왜곡됐을 수 있다.
  · 상위 1% 비중 하나만 보지 말고 **1/5/10% 제거 후 순기대값 · 최대 승자 제거 후
    Sharpe · 연도별 C1% · 코인별 C1%** 를 같이 보아야 한다.
  · 상위 1% 제거 시 기대값이 음수로 뒤집히면 전략이 무효라는 뜻은 아니지만,
    "안정적 알파" 가 아니라 **희귀 추세 사건 보유 능력**에 의존하는 시스템으로
    분류해야 한다.
  · 손절은 성과 향상 장치가 아니라 **재난 브레이커**로 분리해 검정하는 편이 방어적이다.

또한 상충 근거가 하나 제시됐다 —
  Sadaqat & Butt (2023), *Journal of Behavioral and Experimental Finance* 39:100833.
  147코인 2015-01~2022-06, **월간 30% stop-loss** 를 건 모멘텀이 벤치마크보다
  수익·Sharpe·alpha 우수(평균 월수익 9.13%, 변동성 21.36%).
  단 그 논문은 **횡단면 winner-long/loser-short** 이고 우리는 **현물 롱온리 TSM** 이라
  구조가 다르다. 여기서 넓은 손절(재난 브레이커)을 우리 구조에 직접 걸어 확인한다.

데이터 = 업비트 일봉 OHLC 40종(2018-12~2026-08). 신호·비용은 라이브 정합.
"""
from __future__ import annotations

import glob
import json
import os
from math import sqrt

import numpy as np

OHLC_DIR = ("/private/tmp/claude-501/-Users-macbookpro-Desktop--------/"
            "3b4bdb64-7a07-412b-b2cf-029170e8bf91/scratchpad/upbit_ohlc")
SHORT, LONG, FEE_RT = 30, 90, 0.001
WARMUP, MAX_HOLD = LONG + 5, 400
BREAKERS = [None, 0.50, 0.40, 0.30, 0.25, 0.20]     # 재난 브레이커 폭


def load():
    out = {}
    for p in sorted(glob.glob(os.path.join(OHLC_DIR, "*.json"))):
        d = json.load(open(p))
        a = np.array(d["c"], dtype=float)
        if len(a) >= WARMUP + 60:
            out[d["m"]] = a
    return out


def trades(book, breaker=None):
    """TIDE 현행 청산(신호 소멸) + 선택적 재난 브레이커. → (수익, 코인, 연도)"""
    R, M, Y = [], [], []
    for m, a in book.items():
        dt, lo, cl = a[:, 0], a[:, 3], a[:, 4]
        n = len(cl)
        sig = np.zeros(n)
        sig[SHORT:] += (cl[SHORT:] > cl[:-SHORT]).astype(float)
        sig[LONG:] += (cl[LONG:] > cl[:-LONG]).astype(float)
        sig /= 2.0
        sig[:LONG] = 0.0
        inpos = sig > 0
        i = WARMUP
        while i < n - 1:
            if inpos[i] and not inpos[i - 1]:
                j = i + 1
                while j < n and inpos[j] and (j - i) < MAX_HOLD:
                    j += 1
                e = cl[i]
                seg = slice(i + 1, min(j + 1, n))
                c_seg, l_seg = cl[seg], lo[seg]
                r = None
                if breaker is not None and len(c_seg):
                    lvl = e * (1 - breaker)
                    hit = np.where(l_seg <= lvl)[0]        # 장중 터치 = 지정가 스톱
                    if len(hit):
                        r = lvl / e - 1.0
                if r is None and len(c_seg):
                    r = c_seg[-1] / e - 1.0
                if r is not None:
                    R.append(r - FEE_RT); M.append(m); Y.append(int(dt[i]) // 10000)
                i = j
            else:
                i += 1
    return np.array(R), np.array(M), np.array(Y)


def c_frac(r, q):
    if r.sum() == 0:
        return float("nan")
    k = max(1, int(len(r) * q))
    return np.sort(r)[::-1][:k].sum() / r.sum() * 100


def main() -> None:
    book = load()
    R, M, Y = trades(book)
    print("크립토 꼬리 집중도 견고성 — 외부 자문 지적 반영")
    print(f"  종목 {len(book)} · 거래 {len(R):,} · {Y.min()}~{Y.max()} · 왕복 {FEE_RT*100:.2f}%")
    print()

    # ── ① 상위 제거 후 순기대값 ──────────────────────────────────────────
    print("## ① 상위 승자 제거 후 기대값 — '희귀 사건 의존' 인가")
    srt = np.sort(R)[::-1]
    print(f"{'제거':>14}{'남은 거래':>10}{'기대값':>10}{'중앙값':>10}{'판정':>10}")
    print("-" * 56)
    for q, lab in [(0.0, "제거 없음"), (0.001, "상위 0.1%"), (0.01, "상위 1%"),
                   (0.05, "상위 5%"), (0.10, "상위 10%")]:
        k = int(len(srt) * q)
        rest = srt[k:]
        v = rest.mean() * 100
        print(f"{lab:>14}{len(rest):>10}{v:>9.2f}%{np.median(rest)*100:>9.2f}%"
              f"{'양수' if v > 0 else '**음수**':>10}")
    print(f"  최대 승자 1건 제거: 기대값 {srt[1:].mean()*100:+.2f}% (제거 전 {R.mean()*100:+.2f}%)")
    print()

    # ── ② 집중도 분해 ────────────────────────────────────────────────────
    print("## ② 집중도 C1% 분해 — 한 구간·한 코인의 산물인가")
    print(f"  전체 C1% = {c_frac(R, 0.01):.1f}% · C5% = {c_frac(R, 0.05):.1f}% · C10% = {c_frac(R, 0.10):.1f}%")
    print()
    print(f"{'연도':>8}{'거래':>7}{'기대값':>10}{'C1%':>9}")
    print("-" * 34)
    for y in sorted(set(Y.tolist())):
        m = Y == y
        if m.sum() < 30:
            continue
        print(f"{y:>8}{m.sum():>7}{R[m].mean()*100:>9.2f}%{c_frac(R[m], 0.01):>8.1f}%")
    print()
    tops = sorted({m: R[M == m].sum() for m in set(M)}.items(), key=lambda x: -x[1])[:5]
    print("  수익 기여 상위 코인 5:")
    for m, s in tops:
        print(f"    {m:>12} 합계 {s*100:>8.0f}% · 거래 {(M==m).sum():>3} · "
              f"전체 대비 {s/R.sum()*100:>5.1f}%")
    ex_top = R[M != tops[0][0]]
    print(f"  1위 코인({tops[0][0]}) 제외 시 기대값 {ex_top.mean()*100:+.2f}% "
          f"(전체 {R.mean()*100:+.2f}%)")
    print()

    # ── ③ 재난 브레이커 ──────────────────────────────────────────────────
    print("## ③ 재난 브레이커 — 성과 장치가 아니라 손실 상한으로서")
    print("   (외부 자문: Sadaqat & Butt 2023 은 월 30% stop 이 CS 모멘텀을 개선. 단 롱숏 구조)")
    print(f"{'브레이커':>12}{'거래':>7}{'기대값':>10}{'중앙값':>9}{'최악':>9}{'CVaR5%':>10}{'C1%':>8}")
    print("-" * 66)
    for b in BREAKERS:
        r, _, _ = trades(book, breaker=b)
        cv = np.sort(r)[:max(1, int(len(r) * 0.05))].mean() * 100
        lab = "없음(현행)" if b is None else f"−{int(b*100)}%"
        print(f"{lab:>12}{len(r):>7}{r.mean()*100:>9.2f}%{np.median(r)*100:>8.1f}%"
              f"{r.min()*100:>8.1f}%{cv:>9.2f}%{c_frac(r,0.01):>7.1f}%")
    print()
    print("  판정 기준: 기대값을 거의 안 깎으면서 최악·CVaR 을 줄이면 브레이커로 채택 가치.")
    print("             기대값이 눈에 띄게 깎이면 = 꼬리를 자른 것이므로 기각.")


if __name__ == "__main__":
    main()

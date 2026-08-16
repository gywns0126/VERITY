#!/usr/bin/env python3
"""크립토 진입 타이밍 검정 — 꼬리 26건에 타는가 마는가.

## 질문 (PM 2026-08-17): "주식도 있는데 코인은 더더욱이 매매 타이밍이 중요하지 않아?"

직전 검정(`crypto_exit_timing_test.py`)은 **청산** 축만 봤고 "규칙 추가 = 악화" 로 끝냈다.
그런데 같은 검정이 낸 분포가 오히려 PM 지적을 뒷받침한다:

    상위 1%(26거래) = 수익의 90.5% · 최대 1건 +2,195% · 중앙값 −2.2% · 손실 거래 71.1%

**26건에 타느냐가 전부**라는 뜻이고, 그건 청산이 아니라 **진입** 문제다. 청산 결과를
"타이밍은 중요하지 않다" 로 일반화한 것은 과잉이었다. 여기서 진입 축을 친다.

## 직전 검정의 결함 하나 — 레짐 게이트 누락

직전 스크립트는 raw TSM 만 썼다. TIDE 라이브에는 **200일 SMA 자산별 레짐 게이트**
(1.0/0.5, 3일 hysteresis, asymmetric exit)가 있다(origin/main:tide/config.py·regime).
즉 직전 검정은 엄밀히는 TIDE 가 아니었다. 여기서는 게이트를 진입 규칙의 하나로 넣어
실제로 값을 하는지 같이 잰다.

## 측정 원칙 — 꼬리 보존을 1급 지표로

승률·평균만 보면 틀린다. 꼬리를 죽이는 필터는 승률을 올리면서 총수익을 죽인다
(직전 검정에서 트레일링이 정확히 그랬다: 승률 28.9%→33.0%, 손익비 6.69→2.80).
그래서 규칙마다 **상위 1% 기여 · 최대 거래 · 총수익**을 같이 낸다.

청산은 전부 TIDE 현행(신호 소멸 시 청산)으로 고정한다 — 직전 검정에서 최적으로 확인된 값.
따라서 이 검정은 **진입 하나만** 움직인다.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

OHLC_DIR = ("/private/tmp/claude-501/-Users-macbookpro-Desktop--------/"
            "3b4bdb64-7a07-412b-b2cf-029170e8bf91/scratchpad/upbit_ohlc")
LIVE = ("KRW-BTC", "KRW-ETH")
SHORT, LONG, SMA200 = 30, 90, 200
FEE_RT = 0.001
WARMUP = SMA200 + 5
MAX_HOLD = 400


def load(only_live=False):
    out = {}
    for p in sorted(glob.glob(os.path.join(OHLC_DIR, "*.json"))):
        d = json.load(open(p))
        if only_live and d["m"] not in LIVE:
            continue
        a = np.array(d["c"], dtype=float)
        if len(a) >= WARMUP + 120:
            out[d["m"]] = a
    return out


def series(a):
    """→ 종가, 고가, 저가, 신호강도(0/0.5/1.0), 200d 위 여부, 실현변동성"""
    hi, lo, cl = a[:, 2], a[:, 3], a[:, 4]
    n = len(cl)
    sig = np.zeros(n)
    sig[SHORT:] += (cl[SHORT:] > cl[:-SHORT]).astype(float)
    sig[LONG:] += (cl[LONG:] > cl[:-LONG]).astype(float)
    sig /= 2.0
    sig[:LONG] = 0.0
    sma = np.full(n, np.nan)
    c = np.cumsum(np.insert(cl, 0, 0))
    sma[SMA200 - 1:] = (c[SMA200:] - c[:-SMA200]) / SMA200
    above = cl > sma
    r = np.diff(cl, prepend=cl[0]) / np.maximum(cl, 1e-9)
    vol = np.full(n, np.nan)
    for i in range(30, n):
        vol[i] = r[i - 30:i].std()
    return cl, hi, lo, sig, above, vol


# ── 진입 규칙 ─────────────────────────────────────────────────────────────
# 각 규칙은 신호 발생일 t0 를 받아 (실진입 인덱스 or None) 을 돌려준다.
def e_now(t0, cl, sig, above, vol, n):
    return t0


def e_full_signal(t0, cl, sig, above, vol, n):
    """양 룩백 모두 양수(sig=1.0)일 때만. 아니면 그렇게 될 때까지 대기(포지션 유지 중 한정)."""
    for k in range(t0, min(n - 1, t0 + MAX_HOLD)):
        if sig[k] <= 0:
            return None
        if sig[k] >= 1.0:
            return k
    return None


def e_regime(t0, cl, sig, above, vol, n):
    """200일 SMA 위에서만 진입 (TIDE 라이브 레짐 게이트)."""
    return t0 if above[t0] else None


def e_delay(d):
    def f(t0, cl, sig, above, vol, n):
        k = t0 + d
        if k >= n - 1 or sig[k] <= 0:
            return None
        return k
    return f


def e_pullback(pct, wait=10):
    """신호 후 wait 일 내 −pct 되돌림 오면 그 때 진입, 없으면 스킵."""
    def f(t0, cl, sig, above, vol, n):
        ref = cl[t0]
        for k in range(t0 + 1, min(n - 1, t0 + 1 + wait)):
            if sig[k] <= 0:
                return None
            if cl[k] <= ref * (1 - pct):
                return k
        return None
    return f


def e_breakout(pct, wait=10):
    """신호 후 wait 일 내 +pct 추가 상승 확인되면 진입(추세 확인)."""
    def f(t0, cl, sig, above, vol, n):
        ref = cl[t0]
        for k in range(t0 + 1, min(n - 1, t0 + 1 + wait)):
            if sig[k] <= 0:
                return None
            if cl[k] >= ref * (1 + pct):
                return k
        return None
    return f


def e_lowvol(t0, cl, sig, above, vol, n):
    """진입 시점 30일 실현변동성이 자기 이력 중앙값 이하일 때만."""
    v = vol[t0]
    if not np.isfinite(v):
        return None
    ref = np.nanmedian(vol[max(0, t0 - 365):t0 + 1])
    return t0 if np.isfinite(ref) and v <= ref else None


def e_highvol(t0, cl, sig, above, vol, n):
    v = vol[t0]
    if not np.isfinite(v):
        return None
    ref = np.nanmedian(vol[max(0, t0 - 365):t0 + 1])
    return t0 if np.isfinite(ref) and v > ref else None


RULES = [
    ("현행 (신호 즉시)", e_now),
    ("🚨 200d 레짐 게이트", e_regime),
    ("양 룩백 확정(sig=1.0)", e_full_signal),
    ("1일 대기", e_delay(1)),
    ("3일 대기", e_delay(3)),
    ("5일 대기", e_delay(5)),
    ("−5% 되돌림 대기", e_pullback(0.05)),
    ("−10% 되돌림 대기", e_pullback(0.10)),
    ("+5% 추세확인", e_breakout(0.05)),
    ("+10% 추세확인", e_breakout(0.10)),
    ("저변동성 구간만", e_lowvol),
    ("고변동성 구간만", e_highvol),
]


def collect(book, entry_fn):
    """청산은 TIDE 현행 고정. 진입만 규칙에 따라 바꾼다."""
    out = []
    for m, a in book.items():
        cl, hi, lo, sig, above, vol = series(a)
        n = len(cl)
        inpos = sig > 0
        i = WARMUP
        while i < n - 1:
            if inpos[i] and not inpos[i - 1]:
                j = i + 1
                while j < n and inpos[j] and (j - i) < MAX_HOLD:
                    j += 1
                k = entry_fn(i, cl, sig, above, vol, n)
                if k is not None and k < min(j, n - 1):
                    out.append(cl[min(j, n - 1)] / cl[k] - 1.0 - FEE_RT)
                i = j
            else:
                i += 1
    return np.array(out)


def main() -> None:
    print("크립토 진입 타이밍 검정 — 청산은 TIDE 현행 고정, 진입만 바꾼다")
    print(f"  신호 = TSM {SHORT}/{LONG} · 왕복 {FEE_RT*100:.2f}% · 레짐 = {SMA200}d SMA")

    for label, book in [("유니버스 40종 (검정력)", load()),
                        ("KRW-BTC + KRW-ETH (라이브)", load(only_live=True))]:
        base = collect(book, e_now)
        print(f"\n{'='*94}\n## {label} — 종목 {len(book)}")
        print(f"{'진입 규칙':>22}{'거래':>7}{'평균':>9}{'중앙':>8}{'승률':>7}"
              f"{'총수익':>11}{'상위1%비중':>11}{'최대거래':>10}{'±SE':>8}")
        print("-" * 94)
        for name, fn in RULES:
            o = collect(book, fn)
            if len(o) < 15:
                print(f"{name:>22}{len(o):>7}   표본 부족")
                continue
            srt = np.sort(o)[::-1]
            k1 = max(1, int(len(srt) * 0.01))
            tot = srt.sum()
            share = srt[:k1].sum() / tot * 100 if tot != 0 else float("nan")
            se = o.std(ddof=1) / np.sqrt(len(o)) * 100
            print(f"{name:>22}{len(o):>7}{o.mean()*100:>8.2f}%{np.median(o)*100:>7.1f}%"
                  f"{(o>0).mean()*100:>6.1f}%{tot*100:>10.0f}%{share:>10.1f}%"
                  f"{srt[0]*100:>9.0f}%{se:>7.2f}%")
        print()
        print(f"  기준(현행): 거래 {len(base)} · 평균 {base.mean()*100:+.2f}% · "
              f"총수익 {base.sum()*100:.0f}% · 최대 {base.max()*100:.0f}%")
        print("  🚨 총수익·최대거래가 현행보다 크게 낮으면 = 꼬리를 죽인 필터. 평균만 보면 속는다.")


if __name__ == "__main__":
    main()

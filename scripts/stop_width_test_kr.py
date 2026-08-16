#!/usr/bin/env python3
"""손절폭 검정 — KR 주식 (갭 포함). PREREG_VAMS_STOPLOSS_ATR_PRIORITY §9 보류 해제 조건.

크립토 검정(`stop_width_test_crypto.py`)은 24/7 이라 **갭이 없어** VAMS 의 실제 실패 양식
(손절선 −5% 인데 체결 −10.1%)을 재현하지 못했다. 여기서는 그 축을 채운다.

데이터 = `data/kr_chart_daily/` (금융위 주식시세정보, 3,000종목 × 250일, 시가 포함).
**시가가 있어야 갭을 잰다** — 갭 = 전일종가 → 당일시가 점프.

VAMS 실제 기전 재현:
  · VAMS 는 일 1회 사이클에서 **종가** 기준으로 손절을 판정한다.
  · 따라서 종가가 손절선 아래로 갭하락하면 그 종가에 체결된다 → 손절선을 못 지킨다.
  · 이 스크립트는 그 방식(close-based)을 기본으로 하고, 참고로 지정가 스톱
    (장중 터치 시 손절선 체결, 단 시가가 이미 아래면 시가 체결)도 같이 낸다.

핵심 산출:
  ① 같은 평균 손절폭에서 ATR 스케일 vs 고정 % (크립토와 동일 비교)
  ② **갭 슬리피지** = 체결가와 손절선의 괴리. 손절폭이 좁을수록 커지는가?
     ②가 이 검정의 존재 이유다 — 크립토에서 못 본 축.
"""
from __future__ import annotations
import glob
import json
import numpy as np

CHUNKS = "/Users/macbookpro/Desktop/배리티 터미널/data/kr_chart_daily/chunk_*.json"
HOLD = 20
ATR_N = 14
ENTRY_EVERY = 20
WARMUP = 30
MIN_TURNOVER = 3e8      # 진입 시점 직전 20일 중앙 거래대금(원)
FIXED = [0.05, 0.10, 0.15, 0.20]
ATR_K = [1.5, 2.0, 2.5, 3.0]


def load():
    out = []
    for f in sorted(glob.glob(CHUNKS)):
        for tk, v in json.load(open(f))["stocks"].items():
            c = v.get("c") or []
            if len(c) < WARMUP + HOLD + 5:
                continue
            a = np.array(c, dtype=float)      # [날짜, 시, 고, 저, 종, 거래량]
            out.append((tk, v.get("n"), a))
    return out


def build_entries(rows):
    ent = []
    for tk, nm, a in rows:
        o, h, l, c, vol = a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5]
        turn = c * vol
        ret = np.diff(c) / c[:-1]
        for i in range(WARMUP, len(c) - HOLD, ENTRY_EVERY):
            if np.median(turn[i - 20:i]) < MIN_TURNOVER or c[i] <= 0:
                continue
            atr = np.mean(np.abs(ret[i - ATR_N:i]))
            if not np.isfinite(atr) or atr <= 0:
                continue
            ent.append((c[i], atr, o[i + 1:i + 1 + HOLD], l[i + 1:i + 1 + HOLD], c[i + 1:i + 1 + HOLD]))
    return ent


def simulate(ent, width_fn, mode="close"):
    """mode='close'  → VAMS 실제: 종가가 손절선 이하면 그 종가에 체결
       mode='stoporder' → 지정가 스톱: 저가가 손절선 터치 시 손절선 체결, 단 시가가 이미 아래면 시가
       반환 = (수익률, 발동률, 평균폭, 갭슬리피지 배열(%p, 양수=불리))
    """
    outs, gaps, fired, widths = [], [], 0, []
    for e, a, op, lo, cl in ent:
        w = width_fn(a)
        widths.append(w)
        lvl = e * (1 - w)
        idx = np.where(cl <= lvl)[0] if mode == "close" else np.where(lo <= lvl)[0]
        if len(idx):
            j = idx[0]
            fill = cl[j] if mode == "close" else (op[j] if op[j] <= lvl else lvl)
            outs.append(fill / e - 1.0)
            gaps.append((lvl - fill) / e * 100.0)   # 양수 = 손절선보다 나쁘게 체결
            fired += 1
        else:
            outs.append(cl[-1] / e - 1.0)
    return np.array(outs), fired / len(ent), float(np.mean(widths)), np.array(gaps)


def main() -> None:
    rows = load()
    ent = build_entries(rows)
    print(f"KR 일봉 손절폭 검정 — 종목 {len(rows):,} · 진입 표본 {len(ent):,}")
    print(f"ATR(14) 일간 평균변동폭 중앙값 {np.median([e[1] for e in ent])*100:.2f}%")
    print()

    res = {}
    print(f"{'규칙':>12}{'평균폭':>9}{'발동률':>8}{'평균수익':>10}{'하위5%':>10}{'갭슬립p50':>11}{'갭슬립p95':>11}")
    print("-" * 74)
    for f in FIXED:
        o, fr, w, g = simulate(ent, lambda a, f=f: f)
        res[f"고정 -{int(f*100)}%"] = (w, o, g)
        print(f"{'고정 -'+str(int(f*100))+'%':>12}{w*100:>8.1f}%{fr*100:>7.1f}%{o.mean()*100:>9.2f}%"
              f"{np.percentile(o,5)*100:>9.2f}%{np.percentile(g,50):>10.2f}%p{np.percentile(g,95):>10.2f}%p")
    for k in ATR_K:
        o, fr, w, g = simulate(ent, lambda a, k=k: k * a)
        res[f"ATR x{k}"] = (w, o, g)
        print(f"{'ATR x'+str(k):>12}{w*100:>8.1f}%{fr*100:>7.1f}%{o.mean()*100:>9.2f}%"
              f"{np.percentile(o,5)*100:>9.2f}%{np.percentile(g,50):>10.2f}%p{np.percentile(g,95):>10.2f}%p")
    o, fr, w, g = simulate(ent, lambda a: 9.99)
    print(f"{'무손절':>12}{'-':>9}{fr*100:>7.1f}%{o.mean()*100:>9.2f}%{np.percentile(o,5)*100:>9.2f}%")

    print()
    print("## ① 평균 손절폭을 맞춘 짝비교 (크립토와 동일 설계)")
    print(f"{'짝':>28}{'폭차':>8}{'평균수익차':>12}{'하위5%차':>12}")
    print("-" * 62)
    for k in ATR_K:
        wa = res[f"ATR x{k}"][0]
        best = min(FIXED, key=lambda f: abs(res[f"고정 -{int(f*100)}%"][0] - wa))
        oa, of = res[f"ATR x{k}"][1], res[f"고정 -{int(best*100)}%"][1]
        d = abs(res[f"고정 -{int(best*100)}%"][0] - wa)
        print(f"{f'ATR x{k} vs 고정 -{int(best*100)}%':>28}{d*100:>7.1f}%p"
              f"{(oa.mean()-of.mean())*100:>11.2f}%p{(np.percentile(oa,5)-np.percentile(of,5))*100:>11.2f}%p")

    print()
    print("## ② 🚨 갭 슬리피지 — 좁은 손절일수록 커지는가 (크립토에서 못 본 축)")
    print(f"{'손절폭':>10}{'갭슬립 평균':>13}{'p50':>9}{'p95':>9}{'손절폭 대비':>12}")
    print("-" * 54)
    for f in FIXED:
        w, _, g = res[f"고정 -{int(f*100)}%"]
        print(f"{'-'+str(int(f*100))+'%':>10}{g.mean():>12.2f}%p{np.percentile(g,50):>8.2f}%p"
              f"{np.percentile(g,95):>8.2f}%p{g.mean()/(w*100)*100:>11.1f}%")

    print()
    print("## ③ 지정가 스톱이었다면 (참고 — VAMS 는 종가 판정이라 현재는 해당 없음)")
    print(f"{'규칙':>12}{'평균수익':>10}{'갭슬립 평균':>13}")
    print("-" * 36)
    for f in [0.05, 0.10]:
        o, fr, w, g = simulate(ent, lambda a, f=f: f, mode="stoporder")
        print(f"{'고정 -'+str(int(f*100))+'%':>12}{o.mean()*100:>9.2f}%{g.mean():>12.2f}%p")


if __name__ == "__main__":
    main()

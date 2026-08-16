#!/usr/bin/env python3
"""크립토 청산 타이밍 검정 — TIDE 에 손절·익절·트레일링이 있어야 하는가.

## 질문 (PM 2026-08-17): "코인도 주식처럼 매매 타이밍을 정확히 계산해야 하는 거 아님?"

맞는 지적이고, **지금까지 검정된 적이 없다.** TIDE A5 는 손절·익절·트레일링이 **하나도 없다** —
TSM 신호가 꺼지면 나가는 게 청산의 전부다. 반면 같은 세션의 KR 검정(N=129,833)에서는
청산 규칙 하나로 기대값이 +0.270% ~ −0.47% 로 갈렸다. 코인에서 그 축을 처음 친다.

## 왜 지금까지 못 했나 — 데이터

TIDE `cache_ohlcv.parquet` 는 **이름과 달리 close/value 만** 담는다. 고가·저가가 없어
"장중에 손절선을 터치했는가" 를 잴 수 없었다. 그래서 이 스크립트는 업비트 일봉 API 에서
OHLC 를 직접 받아 쓴다(수집 40종 · 91,700봉 · 2018-12~2026-08 · 정합 위반 0).

## 설계

  · 신호 = TIDE 라이브와 동일 dual-lookback TSM 30/90 (origin/main:tide/config.py 정합)
  · 거래 정의 = 신호가 0 → 양수로 바뀌는 날 진입, 신호가 0 으로 돌아오면 청산(= TIDE 현행)
  · 그 위에 청산 규칙을 얹어 비교한다. 손절은 전 규칙 공통이 아니라 **규칙별로** 다르게 둔다
    (현행에는 손절이 아예 없으므로 "손절 없음" 이 baseline 이다)
  · 체결 방식 2종 — 이게 KR 에서 가장 컸던 축이다
      close : 일 1회 종가 판정 (TIDE 현행 사이클)
      stop  : 지정가 스톱 주문 (24/7 이라 갭이 거의 없어 손절선 근처 체결 기대)
  · 비용 = 업비트 KRW 마켓 왕복 0.10% (편도 0.05%)
  · 🚨 유니버스는 생존자 표본이다(신규상장 218 vs 상폐 2). 다만 **생존편향은 모든 규칙에
    동일하게 작용**하므로 규칙 간 **상대 비교**는 견고하고 절대 수익만 부풀려진다.
    KR 재검에서 실측으로 확인됨(편향 영향 −0.008~−0.029%p, 순위 불변).
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
SHORT, LONG = 30, 90          # TIDE origin/main 정합
FEE_RT = 0.001                # 업비트 왕복 0.10%
WARMUP = LONG + 5
MAX_HOLD = 400                # 안전 상한


def load(only_live=False):
    out = {}
    for p in sorted(glob.glob(os.path.join(OHLC_DIR, "*.json"))):
        d = json.load(open(p))
        if only_live and d["m"] not in LIVE:
            continue
        a = np.array(d["c"], dtype=float)
        if len(a) >= WARMUP + 60:
            out[d["m"]] = a
    return out


def trades(book):
    """TIDE 신호 기준 거래 추출 → (진입가, 고가열, 저가열, 종가열, 진입연도)"""
    E, H, L, C, Y = [], [], [], [], []
    for m, a in book.items():
        dt, hi, lo, cl = a[:, 0], a[:, 2], a[:, 3], a[:, 4]
        n = len(cl)
        sig = np.zeros(n)
        for i in range(WARMUP, n):
            s = 1.0 if cl[i] > cl[i - SHORT] else 0.0
            l_ = 1.0 if cl[i] > cl[i - LONG] else 0.0
            sig[i] = (s + l_) / 2.0
        inpos = sig > 0
        i = WARMUP
        while i < n - 1:
            if inpos[i] and not inpos[i - 1]:
                j = i + 1
                while j < n and inpos[j] and (j - i) < MAX_HOLD:
                    j += 1
                seg = slice(i + 1, min(j + 1, n))
                if seg.stop > seg.start:
                    E.append(cl[i]); H.append(hi[seg]); L.append(lo[seg]); C.append(cl[seg])
                    Y.append(int(dt[i]) // 10000)
                i = j
            else:
                i += 1
    return E, H, L, C, np.array(Y)


# ── 청산 규칙 ────────────────────────────────────────────────────────────
def _idx(mask):
    w = np.where(mask)[0]
    return w[0] if len(w) else None


def make_rule(stop=None, target=None, trail=None):
    """stop/target/trail 중 켜진 것만 적용. 전부 None = TIDE 현행(신호 청산만)."""
    def f(e, hi, lo, cl, mode):
        n = len(cl)
        peak = e
        for k in range(n):
            peak = max(peak, hi[k])
            if stop is not None:
                lvl = e * (1 - stop)
                if (cl[k] <= lvl) if mode == "close" else (lo[k] <= lvl):
                    fill = cl[k] if mode == "close" else min(lvl, hi[k])
                    return fill / e - 1.0, (lvl - fill) / e
            if trail is not None:
                lvl = peak * (1 - trail)
                if (cl[k] <= lvl) if mode == "close" else (lo[k] <= lvl):
                    fill = cl[k] if mode == "close" else min(lvl, hi[k])
                    return fill / e - 1.0, (lvl - fill) / e
            if target is not None:
                tg = e * (1 + target)
                if (cl[k] >= tg) if mode == "close" else (hi[k] >= tg):
                    fill = cl[k] if mode == "close" else max(tg, lo[k])
                    return fill / e - 1.0, 0.0
        return cl[-1] / e - 1.0, 0.0
    return f


RULES = [
    ("TIDE 현행 (신호만)", make_rule()),
    ("손절 −10%", make_rule(stop=0.10)),
    ("손절 −15%", make_rule(stop=0.15)),
    ("손절 −20%", make_rule(stop=0.20)),
    ("손절 −30%", make_rule(stop=0.30)),
    ("트레일링 −15%", make_rule(trail=0.15)),
    ("트레일링 −25%", make_rule(trail=0.25)),
    ("트레일링 −35%", make_rule(trail=0.35)),
    ("익절 +30%", make_rule(target=0.30)),
    ("익절 +50%", make_rule(target=0.50)),
    ("손절 −20% + 트레일 −30%", make_rule(stop=0.20, trail=0.30)),
]


def run(E, H, L, C, fn, mode):
    out, gaps = [], []
    for e, hi, lo, cl in zip(E, H, L, C):
        r, g = fn(e, hi, lo, cl, mode)
        out.append(r - FEE_RT)
        if g:
            gaps.append(g * 100)
    return np.array(out), np.array(gaps)


def agg(o):
    win, loss = o[o > 0], o[o < 0]
    wr = len(win) / len(o) * 100 if len(o) else 0
    aw = win.mean() * 100 if len(win) else 0.0
    al = -loss.mean() * 100 if len(loss) else 0.0
    se = o.std(ddof=1) / np.sqrt(len(o)) * 100 if len(o) > 1 else float("nan")
    return o.mean() * 100, wr, (aw / al if al else float("inf")), se


def report(book, title):
    E, H, L, C, Y = trades(book)
    hold = np.mean([len(c) for c in C])
    print(f"\n{'='*82}\n## {title}")
    print(f"  종목 {len(book)} · 거래 {len(E):,} · 평균 보유 {hold:.0f}일 · 진입연도 {Y.min()}~{Y.max()}")
    if len(E) < 20:
        print("  표본 부족 — 비교 불가")
        return None
    print(f"{'규칙':>24}{'종가판정':>10}{'±SE':>8}{'지정가스톱':>11}{'차이':>9}{'승률':>7}{'손익비':>7}")
    print("-" * 82)
    rows = []
    for name, fn in RULES:
        oc, _ = run(E, H, L, C, fn, "close")
        os_, gp = run(E, H, L, C, fn, "stop")
        mc, wr, pr, se = agg(oc)
        ms = agg(os_)[0]
        rows.append((name, mc, ms, wr, pr, se, gp))
        print(f"{name:>24}{mc:>9.2f}%{se:>7.2f}%{ms:>10.2f}%{ms-mc:>8.2f}%p{wr:>6.1f}%{pr:>7.2f}")
    base = rows[0]
    print()
    best_c = max(rows, key=lambda r: r[1]); best_s = max(rows, key=lambda r: r[2])
    print(f"  현행 baseline: {base[1]:+.2f}%/거래 (종가판정)")
    print(f"  종가판정 최고: {best_c[0]} {best_c[1]:+.2f}%  (현행 대비 {best_c[1]-base[1]:+.2f}%p)")
    print(f"  지정가스톱 최고: {best_s[0]} {best_s[2]:+.2f}%  (현행 대비 {best_s[2]-base[2]:+.2f}%p)")
    gaps = np.concatenate([r[6] for r in rows if len(r[6])]) if any(len(r[6]) for r in rows) else np.array([])
    if len(gaps):
        print(f"  🚨 24/7 갭 슬리피지: 평균 {gaps.mean():.2f}%p · p95 {np.percentile(gaps,95):.2f}%p "
              f"(KR 주식 실측 2.44%p 와 대조)")
    return rows, E, H, L, C


def main() -> None:
    print("크립토 청산 타이밍 검정 — TIDE 에 손절·익절이 있어야 하는가")
    print(f"  신호 = dual-lookback TSM {SHORT}/{LONG} (라이브 정합) · 왕복 {FEE_RT*100:.2f}%")

    broad = load()
    r_broad = report(broad, f"유니버스 {len(broad)}종 — 검정력 확보용 (생존자 표본, 상대비교만 유효)")
    r_live = report(load(only_live=True), "KRW-BTC + KRW-ETH — TIDE 라이브 유니버스")

    # ── 왜 그런가 — 이익 꼬리 집중도 ──
    if r_broad:
        rows, E, H, L, C = r_broad
        base = run(E, H, L, C, RULES[0][1], "close")[0]
        srt = np.sort(base)[::-1]
        tot = srt.sum()
        print(f"\n{'='*82}\n## 왜 청산 규칙이 해로운가 — 이익 꼬리 집중도 (현행 기준, 거래 {len(srt):,})")
        print(f"{'상위':>8}{'거래수':>8}{'수익 기여':>12}{'누적 비중':>11}")
        print("-" * 40)
        for q in (0.01, 0.05, 0.10, 0.20, 0.50):
            k = max(1, int(len(srt) * q))
            print(f"{q*100:>7.0f}%{k:>8}{srt[:k].sum()*100:>11.1f}%{srt[:k].sum()/tot*100:>10.1f}%")
        neg = (base < 0).sum()
        print(f"  손실 거래 {neg:,}건({neg/len(base)*100:.1f}%) 합계 {base[base<0].sum()*100:.1f}%")
        print(f"  최대 1건 수익 {srt[0]*100:.0f}% · 중앙값 {np.median(base)*100:+.1f}%")
        print("  → 소수 거래가 전체 수익을 만든다. 익절·트레일링은 바로 그 꼬리를 자른다.")

        # 24/7 갭 — KR 과 직접 대조
        gaps = []
        for e, hi, lo, cl in zip(E, H, L, C):
            lvl = e * (1 - 0.20)
            k = np.where(cl <= lvl)[0]
            if len(k):
                gaps.append((lvl - cl[k[0]]) / e * 100)
        if gaps:
            g = np.array(gaps)
            print(f"\n  🚨 손절 −20% 종가판정 갭 슬리피지: 평균 {g.mean():.2f}%p · p95 "
                  f"{np.percentile(g,95):.2f}%p · 발동 {len(g)}건")
            print(f"     KR 주식 실측 평균 2.44%p 와 대조 — 24/7 이라 갭이 작을 것으로 예상했던 축")

    # ── 선택 게이트 ──
    if r_broad:
        from pbo_selection_gate import pbo_cscv, effective_trials
        rows, E, H, L, C = r_broad
        M = np.column_stack([run(E, H, L, C, fn, "close")[0] for _, fn in RULES])
        ne, mc = effective_trials(M)
        p = pbo_cscv(M, s_blocks=10, ann=1)
        print(f"\n{'='*82}\n## 🚨 선택 게이트 — '최고 규칙' 이 인공물인가")
        print(f"  규칙 {M.shape[1]} · 표본 {M.shape[0]:,} · 상관 평균 {mc:.3f} · N_eff ≈ {ne:.1f}")
        print(f"  PBO = {p:.1%} → " + ("선택 유효" if p < 0.30 else "경계" if p < 0.50 else "FAIL"))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""KR 청산 규칙 재검정 — 6.5년 전 유니버스 + 상장폐지 포함 (생존편향 보정).

## 왜 다시 하나

2026-08-16 세션의 1차 청산 검정(`exit_rule_test_kr.py`)은 입력이
`data/kr_chart_daily/chunk_*.json` 이었다. 그 파일은 **KEEP_DAYS=250 으로 잘린 최근분**
(2025-05-22~2026-08-13, 15개월)이고 **생존 종목만** 담는다. 즉 1차 결론은
"단일 레짐 15개월 · 생존자 표본" 위에 서 있었다.

같은 세션에서 크립토 생존편향(신규상장 218 vs 상폐 2)을 잡아내고도 자기 KR 결론에는
같은 검사를 걸지 않았다. 여기서 그걸 친다.

## 데이터 — 분모를 먼저 밝힌다 (RULE 13)

  · 생존   = Blob `kr_chart_history/<종목>.json` 2,993 / 유니버스 3,000 (실패 7)
             1,614봉 · 2020-01-02 ~ 2026-07-30
             🚨 repo 비커밋(165MB) 이라 로컬에 없다. 250봉 청크만 보고 "15개월치뿐"
             이라고 단정하면 틀린다 — 실제로 이 세션에서 한 번 틀렸다.
  · 상폐   = `data/kr_chart_delisted/*.json` 415종목 · 2020-01-02 ~ 2026-07-30
  · 창     = 두 집합 공통 구간으로 정렬. 상폐 종목은 상장폐지 시점까지만 존재하므로
             자연스럽게 표본에서 빠진다(= 실제 투자자가 겪는 것과 동일).

## 설계

진입 = 20거래일마다 · 보유 최대 20일 · 직전 20일 중앙 거래대금 ≥3억 · 손절 −5% 공통.
1차와 동일 절차를 유지해 **기간·생존편향만** 바뀌게 한다(변수 하나만 움직인다).
"""
from __future__ import annotations

import glob
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))

HIST_DIR = ("/private/tmp/claude-501/-Users-macbookpro-Desktop--------/"
            "3b4bdb64-7a07-412b-b2cf-029170e8bf91/scratchpad/krhist")
DEAD = "data/kr_chart_delisted/*.json"
HOLD, ENTRY_EVERY, WARMUP = 20, 20, 30
MIN_TURNOVER = 3e8
STOP = 0.05

# 거래비용 — 1차 검정에서 누락해 외부 지적을 받은 축. 여기서는 처음부터 넣는다.
#   매수 수수료 0.015% + 매도 수수료 0.015% + 증권거래세 0.18%(2026 KOSPI/KOSDAQ) = 왕복 0.21%
#   부분청산 규칙은 매도가 2회로 나뉘므로 매도측 비용이 한 번 더 붙는다(수수료+세금은 금액 비례라
#   총액은 같으나, 잔여분을 끝까지 들고 가므로 실질 동일 — 보수적으로 반쪽 매도 1회를 추가 부과).
FEE_BUY, FEE_SELL = 0.00015, 0.00015 + 0.0018
ROUND_TRIP = FEE_BUY + FEE_SELL              # 0.21%
PARTIAL_EXTRA = FEE_SELL * 0.5               # 부분청산 추가 매도 레그


def load_hist(d):
    out = {}
    for p in glob.glob(os.path.join(d, "*.json")):
        try:
            c = json.load(open(p)).get("c") or []
        except Exception:
            continue
        if len(c) >= WARMUP + HOLD + 5:
            out[Path(p).stem] = np.array(c, dtype=float)
    return out


def load_dead(pat):
    out = {}
    for f in sorted(glob.glob(pat)):
        for tk, v in json.load(open(f)).get("stocks", {}).items():
            c = v.get("c") or []
            if len(c) >= WARMUP + HOLD + 5:
                out[tk] = np.array(c, dtype=float)
    return out


def build(book):
    """→ (진입가, 고가행렬, 저가행렬, 종가행렬, 진입연도)"""
    E, H, L, C, Y = [], [], [], [], []
    for tk, a in book.items():
        hi, lo, cl, vol = a[:, 2], a[:, 3], a[:, 4], a[:, 5]
        dt = a[:, 0]
        turn = cl * vol
        for i in range(WARMUP, len(cl) - HOLD, ENTRY_EVERY):
            if cl[i] <= 0 or np.median(turn[i - 20:i]) < MIN_TURNOVER:
                continue
            s = slice(i + 1, i + 1 + HOLD)
            E.append(cl[i]); H.append(hi[s]); L.append(lo[s]); C.append(cl[s])
            Y.append(int(dt[i]) // 10000)
    if not E:
        return (np.zeros((0,)),) * 4 + (np.zeros((0,), dtype=int),)
    return (np.array(E), np.array(H), np.array(L), np.array(C), np.array(Y))


# ── 청산 규칙 (전부 벡터화) ───────────────────────────────────────────────
def _first(mask):
    """행별 첫 True 인덱스, 없으면 -1"""
    any_ = mask.any(axis=1)
    idx = mask.argmax(axis=1)
    return np.where(any_, idx, -1)


def r_none(E, H, L, C):
    js = _first(L <= E[:, None] * (1 - STOP))
    return np.where(js >= 0, -STOP, C[:, -1] / E - 1)


def r_target(mult, partial):
    def f(E, H, L, C):
        js = _first(L <= E[:, None] * (1 - STOP))
        jt = _first(H >= E[:, None] * (1 + STOP * mult))
        base = np.where(js >= 0, -STOP, C[:, -1] / E - 1)
        hit = (jt >= 0) & ((js < 0) | (jt <= js))
        if partial >= 1.0:
            return np.where(hit, STOP * mult, base)
        # 부분청산 후 잔여분: 목표 도달 이후 구간에서 손절 or 최종종가
        n = len(E)
        rest = np.empty(n)
        cols = np.arange(H.shape[1])[None, :]
        after = cols > jt[:, None]
        stop_after = ((L <= E[:, None] * (1 - STOP)) & after).any(axis=1)
        rest = np.where(stop_after, -STOP, C[:, -1] / E - 1)
        combo = partial * (STOP * mult) + (1 - partial) * rest
        return np.where(hit, combo, base)
    return f


def r_trail(t):
    def f(E, H, L, C):
        peak = np.maximum.accumulate(np.maximum(H, E[:, None]), axis=1)
        lvl = peak * (1 - t)
        hit_t = _first(L <= lvl)
        hit_s = _first(L <= E[:, None] * (1 - STOP))
        n = len(E)
        out = C[:, -1] / E - 1
        stop_first = (hit_s >= 0) & ((hit_t < 0) | (hit_s <= hit_t))
        trail_first = (hit_t >= 0) & ~stop_first
        out = np.where(stop_first, -STOP, out)
        if trail_first.any():
            r = np.arange(n)[trail_first]
            px = peak[r, hit_t[trail_first]] * (1 - t)
            out[trail_first] = np.maximum(px / E[trail_first] - 1, -STOP)
        return out
    return f


RULES = [
    ("익절 없음(20일)", r_none, ROUND_TRIP),
    ("+1R 전량", r_target(1.0, 1.0), ROUND_TRIP),
    ("+1R 절반 (VAMS 현행)", r_target(1.0, 0.5), ROUND_TRIP + PARTIAL_EXTRA),
    ("+2R 절반", r_target(2.0, 0.5), ROUND_TRIP + PARTIAL_EXTRA),
    ("트레일링 −3%", r_trail(0.03), ROUND_TRIP),
    ("트레일링 −5%", r_trail(0.05), ROUND_TRIP),
    ("트레일링 −8%", r_trail(0.08), ROUND_TRIP),
    ("트레일링 −12%", r_trail(0.12), ROUND_TRIP),
]


def agg(out):
    win, loss = out[out > 0], out[out < 0]
    wr = len(win) / len(out) * 100 if len(out) else 0
    aw = win.mean() * 100 if len(win) else 0.0
    al = -loss.mean() * 100 if len(loss) else 0.0
    se = out.std(ddof=1) / np.sqrt(len(out)) * 100 if len(out) > 1 else float("nan")
    return out.mean() * 100, wr, (aw / al if al else float("inf")), se


def main() -> None:
    live, dead = load_hist(HIST_DIR), load_dead(DEAD)
    print("KR 청산 규칙 재검정 — 6.5년 · 생존편향 보정")
    print(f"  생존 {len(live):,}종목 (Blob kr_chart_history · 유니버스 3,000 중 다운로드 성공분)")
    print(f"  상폐 {len(dead):,}종목 (data/kr_chart_delisted)")

    L = build(live)
    D = build(dead)
    A = tuple(np.concatenate([a, b]) for a, b in zip(L, D))
    print(f"  진입 표본: 생존 {len(L[0]):,} · 상폐 {len(D[0]):,} · 합계 {len(A[0]):,}"
          f"  (상폐 비중 {len(D[0])/len(A[0])*100:.2f}%)")
    print(f"  진입 연도 범위 {A[4].min()}~{A[4].max()} · 손절 −{STOP*100:.0f}% 공통 · 최대 {HOLD}일")
    print(f"  🚨 거래비용 반영: 왕복 {ROUND_TRIP*100:.2f}% (수수료 0.03% + 거래세 0.18%) · 부분청산 +{PARTIAL_EXTRA*100:.2f}%")
    print()

    print("## 전 기간 (2020~2026)")
    print(f"{'규칙':>22}{'생존만':>10}{'상폐포함':>11}{'차이':>10}{'승률':>8}{'손익비':>8}{'±SE':>9}")
    print("-" * 78)
    rows = []
    for name, fn, cost in RULES:
        ev_l = agg(fn(*L[:4]) - cost)[0]
        m, wr, pr, se = agg(fn(*A[:4]) - cost)
        rows.append((name, ev_l, m, wr, pr, se))
        print(f"{name:>22}{ev_l:>9.3f}%{m:>10.3f}%{m-ev_l:>9.3f}%p{wr:>7.1f}%{pr:>8.2f}{se:>8.3f}%")

    b_l = max(rows, key=lambda r: r[1]); b_a = max(rows, key=lambda r: r[2])
    print()
    print(f"  생존만 최고 = {b_l[0]} ({b_l[1]:+.3f}%) · 상폐포함 최고 = {b_a[0]} ({b_a[2]:+.3f}%)")
    print(f"  → 생존편향 영향 {'없음(결론 유지)' if b_a[0] == b_l[0] else '**결론 뒤집힘**'}")
    print()

    # ── 연도별 안정성 — 1차 검정이 못 본 축 ──
    print("## 연도별 기대값 (%/거래) — 단일 레짐 결론인지 본다")
    yrs = sorted(set(A[4].tolist()))
    print(f"{'규칙':>22}" + "".join(f"{y:>9}" for y in yrs))
    print("-" * (22 + 9 * len(yrs)))
    yearly = {}
    for name, fn, cost in RULES:
        o = fn(*A[:4]) - cost
        vals = [o[A[4] == y].mean() * 100 if (A[4] == y).sum() > 30 else float("nan") for y in yrs]
        yearly[name] = vals
        print(f"{name:>22}" + "".join(f"{v:>8.2f}%" for v in vals))
    print()
    print(f"{'규칙':>22}{'양수 연도':>11}{'연도 최악':>11}{'연도 표준편차':>14}")
    print("-" * 58)
    for name, vals in yearly.items():
        v = np.array([x for x in vals if np.isfinite(x)])
        print(f"{name:>22}{f'{(v>0).sum()}/{len(v)}':>11}{v.min():>10.2f}%{v.std():>13.2f}%p")

    print()
    print("## 손익비 본전 조건 (VAMS 승률 26.1% → 필요 2.83)")
    for name, ev_l, m, wr, pr, se in rows:
        need = (100 - wr) / wr if wr else float("inf")
        print(f"  {'✅' if pr >= need else '❌'} {name:>22} 승률 {wr:5.1f}% → 필요 {need:5.2f} · 실제 {pr:5.2f}")

    # ── 🚨 자기 결론에 자기 게이트를 건다 ──────────────────────────────────
    # "익절 없음이 최고" 라는 결론 자체가 8개 규칙 중 최고를 고른 **선택**이다.
    # 오늘 크립토에서 세운 규율(선택은 PBO 로 검정한다)을 자기 결론에 적용하지 않으면
    # 규율이 아니라 남에게만 쓰는 잣대가 된다.
    from pbo_selection_gate import pbo_cscv, effective_trials   # noqa: E402

    print()
    print("## 🚨 자기 게이트 적용 — '익절 없음 최고' 가 선택 인공물인가")
    yq = A[4]                     # 진입 연도
    # 연-분기 대용으로 연도만 쓰면 블록이 7개뿐 → 진입 순서를 시간축으로 삼아 균등 분할
    order = np.argsort(yq, kind="stable")
    M = np.column_stack([fn(*A[:4])[order] - cost for _, fn, cost in RULES])
    n_eff, mcorr = effective_trials(M)
    p = pbo_cscv(M, s_blocks=10, ann=1)     # 거래 단위라 연율화 불필요
    print(f"  규칙 {M.shape[1]}개 · 표본 {M.shape[0]:,} · 규칙 간 상관 평균 {mcorr:.3f} · N_eff ≈ {n_eff:.1f}")
    print(f"  PBO = {p:.1%}", end="  ")
    print("→ 선택 유효" if p < 0.30 else ("→ 경계" if p < 0.50 else "→ FAIL, 최고값 채택 금지"))
    print("  (규칙 간 상관이 높은 건 같은 진입·같은 손절을 공유하기 때문이다 — 정상)")


if __name__ == "__main__":
    main()

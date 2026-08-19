#!/usr/bin/env python3
"""손절 효능이 변동성(MAX) 조건부인가 — 연도별 안정성 검정.

## 왜 이 검정인가

`docs/MAX_HORIZON_SIZING_RESEARCH_2026_08_19.md` §2 의 결론은
"손절은 고MAX 구간에서만 이득이고 저MAX 구간에서는 파괴적" 이었다. 그 문서가 실제로
연도별 안정성을 검정한 대상은 §3-B 의 **다른 주장**(중간 MAX 최적 보유지평)이었고
그건 6년 중 3년 실패해 채택 불가로 판정됐다.

즉 **정작 손절폭을 걸려는 주장 자체는 전 기간 평균 하나로만 서 있다.**
같은 문서 안에서 이웃 주장이 연도별로 무너진 걸 봤으면 이 주장도 같은 검사를 통과해야 한다.
여기서 그걸 친다. 통과 못 하면 사전등록 대상에서 뺀다.

## 분모 (RULE 13 — 열거 먼저)

  · 생존 = Blob `kr_chart_history/*.json` (스크래치패드 캐시) — 실제 로드 수를 출력한다
  · 상폐 = `data/kr_chart_delisted/*.json` — 생존편향 보정. 이걸 빼면 손절 규칙 비교는
           구조적으로 무손절에 유리해진다(망한 종목이 표본에서 사라지므로)
  · 진입 = 20거래일 간격 · 직전 20일 중앙 거래대금 ≥3억 · 보유 최대 20일
  · 비용 = 왕복 0.21% (수수료 0.03% + 거래세 0.18%) 전 규칙 동일 부과

## MAX 정의와 분위 배정

MAX = 진입 **직전** 20거래일의 일수익률 최대값 (Bali et al. 복권효과 지표).
분위는 **진입일 횡단면 내부**에서 매긴다 — 전 기간 통합 분위로 매기면 변동성이 높은
연도(2020·2022)가 통째로 상위 분위에 몰려 "MAX 효과" 와 "연도 효과" 가 섞인다.
이 검정의 질문이 정확히 연도 안정성이므로 그 혼입을 먼저 제거해야 한다.
"""
from __future__ import annotations

import glob
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

HIST_DIR = ("/private/tmp/claude-501/-Users-macbookpro-Desktop--------/"
            "3b4bdb64-7a07-412b-b2cf-029170e8bf91/scratchpad/krhist")
DEAD = "data/kr_chart_delisted/*.json"
HOLD, ENTRY_EVERY, WARMUP = 20, 20, 30
MIN_TURNOVER = 3e8
MAX_LOOKBACK = 20
N_Q = 5
MIN_PER_DATE = 50          # 횡단면 분위를 매기려면 그날 진입 후보가 최소 이만큼
ROUND_TRIP = 0.00015 + 0.00015 + 0.0018      # 0.21%


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
    """진입 표본 → (E, H, L, C, year, date, maxret)"""
    E, H, L, C, Y, D, M = [], [], [], [], [], [], []
    for _tk, a in book.items():
        hi, lo, cl, vol, dt = a[:, 2], a[:, 3], a[:, 4], a[:, 5], a[:, 0]
        turn = cl * vol
        with np.errstate(divide="ignore", invalid="ignore"):
            dret = np.diff(cl) / cl[:-1]          # dret[k] = k→k+1 수익률
        for i in range(WARMUP, len(cl) - HOLD, ENTRY_EVERY):
            if cl[i] <= 0 or np.median(turn[i - 20:i]) < MIN_TURNOVER:
                continue
            w = dret[i - MAX_LOOKBACK:i]          # 진입 직전 20일, 진입일 미포함
            if len(w) < MAX_LOOKBACK or not np.isfinite(w).all():
                continue
            s = slice(i + 1, i + 1 + HOLD)
            E.append(cl[i]); H.append(hi[s]); L.append(lo[s]); C.append(cl[s])
            D.append(int(dt[i])); Y.append(int(dt[i]) // 10000); M.append(float(w.max()))
    if not E:
        raise SystemExit("진입 표본 0 — 입력 경로 확인")
    return (np.array(E), np.array(H), np.array(L), np.array(C),
            np.array(Y), np.array(D), np.array(M))


# ── 청산 규칙 (벡터화) ────────────────────────────────────────────────────
def _first(mask):
    any_ = mask.any(axis=1)
    return np.where(any_, mask.argmax(axis=1), -1)


def r_hold(E, H, L, C):
    return C[:, -1] / E - 1


def r_stop(s):
    def f(E, H, L, C):
        js = _first(L <= E[:, None] * (1 - s))
        return np.where(js >= 0, -s, C[:, -1] / E - 1)
    return f


def r_trail(t):
    """진입가에서 시작하는 순수 트레일링 — 초기에는 −t 하드손절과 동일하다."""
    def f(E, H, L, C):
        peak = np.maximum.accumulate(np.maximum(H, E[:, None]), axis=1)
        hit = _first(L <= peak * (1 - t))
        out = C[:, -1] / E - 1
        if hit.max() >= 0:
            r = np.arange(len(E))[hit >= 0]
            px = peak[r, hit[hit >= 0]] * (1 - t)
            out[hit >= 0] = px / E[hit >= 0] - 1
        return out
    return f


RULES = [
    ("무손절", r_hold),
    ("손절 −5%", r_stop(0.05)),
    ("손절 −10%", r_stop(0.10)),
    ("손절 −15%", r_stop(0.15)),
    ("트레일 −5%", r_trail(0.05)),
    ("트레일 −10%", r_trail(0.10)),
]


def cross_sectional_quintiles(dates, maxret):
    """진입일 횡단면 내부 분위. 후보가 MIN_PER_DATE 미만인 날은 제외(-1)."""
    q = np.full(len(dates), -1, dtype=int)
    for d in np.unique(dates):
        idx = np.flatnonzero(dates == d)
        if len(idx) < MIN_PER_DATE:
            continue
        r = maxret[idx].argsort().argsort()          # 0..n-1 랭크
        q[idx] = np.minimum((r * N_Q) // len(idx), N_Q - 1)
    return q


def pooled_quintiles(dates, maxret):
    """전 기간 통합 분위 — 종전 검정이 쓴 방식. 비교용으로만 둔다."""
    r = maxret.argsort().argsort()
    return np.minimum((r * N_Q) // len(maxret), N_Q - 1)


def main() -> None:
    pooled = "--pooled" in sys.argv
    surv_only = "--survivors-only" in sys.argv     # 종전 §2 재현용 — 생존편향 격리
    live, dead = load_hist(HIST_DIR), load_dead(DEAD)
    Lb, Db = build(live), build(dead)
    if surv_only:
        print("[🚨 생존자만 — 상폐 제외. 종전 §2 조건 재현용이며 편향된 표본이다]")
        Db = tuple(a[:0] for a in Db)
    A = tuple(np.concatenate([a, b]) for a, b in zip(Lb, Db))
    E, H, L, C, Y, DT, MX = A

    q = pooled_quintiles(DT, MX) if pooled else cross_sectional_quintiles(DT, MX)
    print(f"[분위 배정 = {'전 기간 통합(pooled) — 종전 방식' if pooled else '진입일 횡단면 — 기본'}]")
    keep = q >= 0
    dropped_dates = len(np.unique(DT)) - len(np.unique(DT[keep]))

    print("손절 효능의 MAX 조건부성 — 연도별 안정성 검정")
    print(f"  생존 {len(live):,}종목 · 상폐 {len(dead):,}종목 (생존편향 보정)")
    print(f"  진입 후보 {len(E):,} (생존 {len(Lb[0]):,} + 상폐 {len(Db[0]):,}"
          f" · 상폐 비중 {len(Db[0])/len(E)*100:.2f}%)")
    print(f"  횡단면 분위 배정 성공 {keep.sum():,} / {len(E):,}"
          f" ({keep.sum()/len(E)*100:.1f}%) — 후보<{MIN_PER_DATE} 인 진입일 {dropped_dates}개 제외")
    print(f"  진입일 {len(np.unique(DT[keep]))}개 · 연도 {Y[keep].min()}~{Y[keep].max()}"
          f" · 비용 왕복 {ROUND_TRIP*100:.2f}%")

    E, H, L, C, Y, MX, q = E[keep], H[keep], L[keep], C[keep], Y[keep], MX[keep], q[keep]
    DTk = DT[keep]

    # 규칙별 수익 행렬 (비용 차감)
    ret = {name: fn(E, H, L, C) - ROUND_TRIP for name, fn in RULES}

    print("\n## MAX 분위 정의 확인 (진입 직전 20일 최대 일수익률)")
    print(f"{'분위':>6}{'표본':>10}{'MAX 중앙':>11}{'MAX 평균':>11}")
    for k in range(N_Q):
        m = q == k
        print(f"  Q{k+1:<3}{m.sum():>10,}{np.median(MX[m])*100:>10.2f}%{MX[m].mean()*100:>10.2f}%")

    # ── 전 기간 ────────────────────────────────────────────────────────────
    print("\n## 전 기간 — 분위 × 규칙 평균 수익 (20일 보유 · 비용 후)")
    hdr = "".join(f"{n:>13}" for n, _ in RULES)
    print(f"{'분위':>6}{hdr}")
    print("-" * (6 + 13 * len(RULES)))
    base_all = {}
    for k in range(N_Q):
        m = q == k
        base_all[k] = ret["무손절"][m].mean()
        line = "".join(f"{ret[n][m].mean()*100:>12.3f}%" for n, _ in RULES)
        print(f"  Q{k+1:<3}{line}")

    print("\n## 전 기간 — Δ(규칙 − 무손절), 짝지은 차이의 ±SE")
    print(f"{'분위':>6}" + "".join(f"{n:>20}" for n, _ in RULES[1:]))
    print("-" * (6 + 20 * (len(RULES) - 1)))
    for k in range(N_Q):
        m = q == k
        cells = []
        for n, _ in RULES[1:]:
            d = ret[n][m] - ret["무손절"][m]
            se = d.std(ddof=1) / np.sqrt(len(d))
            cells.append(f"{d.mean()*100:>+8.3f}%p±{se*100:.3f}")
        print(f"  Q{k+1:<3}" + "".join(f"{c:>20}" for c in cells))

    # ── 위험 축 ────────────────────────────────────────────────────────────
    # 평균만 보고 "손절 불필요" 로 가면 안 된다. 손절의 값어치는 평균이 아니라 꼬리와
    # 낙폭에서 나온다 — 거래단위 평균과 포트폴리오 종점은 다른 질문이다(TIDE 에서 한 번 혼동함).
    print("\n## 위험 축 — 왼쪽 꼬리 (전 분위 통합)")
    print(f"{'규칙':>14}{'평균':>10}{'표준편차':>11}{'P5':>10}{'P1':>10}{'최악':>10}{'≤−20% 비율':>13}")
    print("-" * 78)
    for n, _ in RULES:
        r = ret[n]
        print(f"{n:>14}{r.mean()*100:>9.3f}%{r.std(ddof=1)*100:>10.2f}%"
              f"{np.percentile(r,5)*100:>9.2f}%{np.percentile(r,1)*100:>9.2f}%"
              f"{r.min()*100:>9.2f}%{(r<=-0.20).mean()*100:>12.2f}%")

    # 포트폴리오 종점 — 진입일별 동일가중 바스켓을 20일마다 굴린 누적 (겹침 없음)
    print("\n## 위험 축 — 포트폴리오 종점 (진입일별 동일가중 · 20일 주기 재투자)")
    print(f"{'규칙':>14}{'누적':>11}{'주기평균':>11}{'MDD':>10}{'주기수':>8}")
    print("-" * 54)
    dts = np.unique(DTk)
    for n, _ in RULES:
        per = np.array([ret[n][DTk == d].mean() for d in dts])
        eq = np.cumprod(1 + per)
        mdd = (eq / np.maximum.accumulate(eq) - 1).min()
        print(f"{n:>14}{(eq[-1]-1)*100:>10.2f}%{per.mean()*100:>10.3f}%"
              f"{mdd*100:>9.2f}%{len(per):>8}")

    # ── 연도별 ─────────────────────────────────────────────────────────────
    years = sorted(set(Y.tolist()))
    print("\n## 연도별 Δ(규칙 − 무손절) — 부호가 매년 같은가")
    for n, _ in RULES[1:]:
        print(f"\n  ▸ {n}")
        print(f"{'분위':>8}" + "".join(f"{y:>10}" for y in years) + f"{'부호일치':>12}")
        for k in range(N_Q):
            cells, signs = [], []
            for y in years:
                m = (q == k) & (Y == y)
                if m.sum() < 30:
                    cells.append(f"{'n<30':>10}")
                    continue
                d = (ret[n][m] - ret["무손절"][m]).mean()
                cells.append(f"{d*100:>+9.2f}p")
                signs.append(np.sign(d))
            full = np.sign(sum(signs)) if signs else 0
            agree = sum(1 for s in signs if s == full and s != 0)
            print(f"      Q{k+1:<3}" + "".join(cells) + f"{agree:>8}/{len(signs)}")


if __name__ == "__main__":
    main()

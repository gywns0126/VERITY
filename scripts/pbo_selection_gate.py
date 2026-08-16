#!/usr/bin/env python3
"""파라미터 선택 게이트 — DSR 이 못 잡는 과최적화를 PBO 로 잡는다.

## 왜 만들었나 (2026-08-16)

크립토 TSM 룩백 52변형에 DSR(`dsr_multiple_testing_gate.py`)을 걸었더니 **1.000 통과**가 나왔다.
그런데 같은 데이터에서 IS↔OOS Sharpe 상관은 **−0.165(R²=0.027)** 였다 — IS 성적이 OOS 를
전혀 예측하지 못하는데 게이트는 통과시킨 것이다.

원인 = **DSR 의 전제 위반**. DSR 은 시행 Sharpe 의 표준편차를 귀무 산포로 삼는데, 같은
전략군의 파라미터 변형들은 서로 강상관(측정값 평균 0.906)이라 그 표준편차가 실제 표집
변동을 크게 과소평가한다. 유효 독립 시행수는 명목 52 가 아니라 **≈7** 이었다. 그런데
N_eff=7 을 넣어도 DSR 은 여전히 1.000 — **어느 N 을 넣어도 통과한다.**

두 도구가 다른 질문에 답하기 때문이다.

| 질문 | 도구 |
|---|---|
| 이 전략군이 실재하는가 | DSR · 벤치마크 대비 |
| IS 로 고른 파라미터가 OOS 에서도 유효한가 | **PBO · IS↔OOS 상관**  ← 이 파일 |
| 실전에서 무엇을 쓰는가 | **롤링 워크포워드**            ← 이 파일 |

**그러므로 DSR 단독 통과를 근거로 파라미터를 채택하지 말 것.** 이 게이트를 병기한다.

## 쓰는 법

    from pbo_selection_gate import selection_gate
    report = selection_gate(M, labels)   # M = (T일 × N변형) 일수익 행렬
    print(report.render())
    if not report.selection_is_valid:
        ...  # 격자 최고값 채택 금지 → 앙상블 또는 현행 유지

참조: Bailey, Borwein, López de Prado, Zhu (2017) "The Probability of Backtest
Overfitting", *Journal of Computational Finance* 20(4):39-69 (CSCV).
Li & Ji (2005) *Heredity* 95:221-227 (고유값 기반 유효 시행수).
검정 사례 = `docs/academic_grounding_library_2026_06_13.md` 영역 15.
"""
from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from math import sqrt

import numpy as np

ANN_DEFAULT = 365          # 크립토 24/7. KR 주식이면 252 를 넘길 것

# 판정 임계 — 사전 고정. 데이터를 보고 조정하지 말 것 (RULE 7).
PBO_FAIL = 0.50            # 이 이상이면 선택이 동전던지기
PBO_WARN = 0.30
R2_MIN = 0.10              # IS↔OOS R² 가 이 아래면 선택 근거 없음


@dataclass
class GateReport:
    n_trials: int
    n_eff: float
    mean_corr: float
    pbo: float
    is_oos_r: float
    walkforward: dict = field(default_factory=dict)
    labels: list = field(default_factory=list)
    best_label: str = ""

    @property
    def selection_is_valid(self) -> bool:
        """격자 최고값을 채택해도 되는가."""
        return self.pbo < PBO_WARN and self.is_oos_r**2 >= R2_MIN

    def render(self) -> str:
        L = []
        L.append(f"## 파라미터 선택 게이트 — 변형 {self.n_trials}개")
        L.append(f"  변형 간 수익 상관 평균 {self.mean_corr:.3f} · 유효 독립 시행수 N_eff ≈ {self.n_eff:.1f}")
        if self.mean_corr > 0.5:
            L.append(f"  🚨 강상관 — DSR 의 독립 전제가 깨진다. DSR 결과를 선택 근거로 쓰지 말 것.")
        L.append("")
        L.append(f"  PBO = {self.pbo:.1%}  (IS 최적이 OOS 중앙값 아래로 갈 확률)")
        L.append(f"  IS↔OOS Sharpe 상관 {self.is_oos_r:+.3f} (R²={self.is_oos_r**2:.3f})")
        L.append("")
        if self.pbo >= PBO_FAIL:
            v = "❌ FAIL — 선택이 동전던지기. 격자 최고값 채택 금지."
        elif self.pbo >= PBO_WARN:
            v = "⚠️ 경계 — IS 최적이 절반 가까이 무너진다. 앙상블 또는 현행 유지 권고."
        elif self.is_oos_r**2 < R2_MIN:
            v = f"⚠️ 경계 — PBO 는 낮으나 IS↔OOS R²={self.is_oos_r**2:.3f} < {R2_MIN}. 선택 근거 약함."
        else:
            v = "✅ 선택 유효 — IS 최적 채택 가능."
        L.append(f"  판정: {v}")
        if self.walkforward:
            L.append("")
            L.append("  롤링 워크포워드 (Sharpe)")
            for k, s in self.walkforward.items():
                L.append(f"    {k:>22} {s:>6.2f}")
        return "\n".join(L)


def _sharpe(r: np.ndarray, ann: int) -> float:
    r = r[np.isfinite(r)]
    if len(r) < 30 or r.std() == 0:
        return float("nan")
    return float(r.mean() / r.std() * sqrt(ann))


def effective_trials(M: np.ndarray) -> tuple[float, float]:
    """수익 상관행렬 고유값 기반 유효 독립 시행수 (Li & Ji 2005). → (N_eff, 평균상관)"""
    C = np.corrcoef(M.T)
    n = C.shape[0]
    off = C[np.triu_indices(n, 1)]
    ev = np.linalg.eigvalsh(C)
    ev = ev[ev > 0]
    n_eff = float(sum((1 if e >= 1 else 0) + (e - np.floor(e)) for e in ev))
    return n_eff, float(off.mean())


def pbo_cscv(M: np.ndarray, s_blocks: int = 10, ann: int = ANN_DEFAULT) -> float:
    """PBO — 시계열을 s블록으로 나눠 절반 IS / 절반 OOS 인 모든 조합에서
    'IS 최적이 OOS 중앙값 아래' 비율. Sharpe 분포가 아닌 **순위**로 판정하므로
    변형 간 상관에 DSR 보다 훨씬 덜 민감하다."""
    T, N = M.shape
    blocks = np.array_split(np.arange(T), s_blocks)
    half = s_blocks // 2
    below = 0
    combos = list(itertools.combinations(range(s_blocks), half))
    for c in combos:
        i_idx = np.concatenate([blocks[i] for i in c])
        o_idx = np.concatenate([blocks[i] for i in range(s_blocks) if i not in c])
        s_is = np.array([_sharpe(M[i_idx, j], ann) for j in range(N)])
        s_oos = np.array([_sharpe(M[o_idx, j], ann) for j in range(N)])
        best = int(np.nanargmax(s_is))
        if (np.sum(s_oos > s_oos[best]) + 1) / (N + 1) > 0.5:
            below += 1
    return below / len(combos)


def walk_forward(M: np.ndarray, train: int = 730, step: int = 91,
                 fixed_col: int | None = None, benchmark: np.ndarray | None = None,
                 ann: int = ANN_DEFAULT) -> dict:
    """실전 절차 그대로: 직전 `train`일로 재선택 → 다음 `step`일을 실제로 먹는다.
    (A) IS 최적 재선택 vs (B) 전체 앙상블 vs (C) 고정 파라미터 vs (D) 벤치마크."""
    T, N = M.shape
    ens = M.mean(axis=1)
    acc: dict[str, list] = {"IS 최적 재선택": [], "격자 전체 앙상블": []}
    if fixed_col is not None:
        acc["고정 파라미터"] = []
    if benchmark is not None:
        acc["벤치마크"] = []
    t = train
    while t + step <= T:
        tr, te = slice(t - train, t), slice(t, t + step)
        s_tr = np.array([_sharpe(M[tr, j], ann) for j in range(N)])
        acc["IS 최적 재선택"].append(M[te, int(np.nanargmax(s_tr))])
        acc["격자 전체 앙상블"].append(ens[te])
        if fixed_col is not None:
            acc["고정 파라미터"].append(M[te, fixed_col])
        if benchmark is not None:
            acc["벤치마크"].append(benchmark[te])
        t += step
    return {k: _sharpe(np.concatenate(v), ann) for k, v in acc.items() if v}


def selection_gate(M: np.ndarray, labels: list[str] | None = None, *,
                   is_frac: float = 0.68, s_blocks: int = 10,
                   fixed_col: int | None = None, benchmark: np.ndarray | None = None,
                   train: int = 730, step: int = 91,
                   ann: int = ANN_DEFAULT) -> GateReport:
    """M = (T일 × N변형) 일수익 행렬. 파라미터 선택이 정당한지 판정한다."""
    M = np.asarray(M, dtype=float)
    M = M[~np.isnan(M).any(axis=1)]
    T, N = M.shape
    if N < 3:
        raise ValueError("변형이 3개 미만이면 선택 게이트가 의미 없다")
    labels = labels or [f"v{i}" for i in range(N)]

    n_eff, mean_corr = effective_trials(M)
    cut = int(T * is_frac)
    s_is = np.array([_sharpe(M[:cut, j], ann) for j in range(N)])
    s_oos = np.array([_sharpe(M[cut:, j], ann) for j in range(N)])
    ok = np.isfinite(s_is) & np.isfinite(s_oos)
    r = float(np.corrcoef(s_is[ok], s_oos[ok])[0, 1]) if ok.sum() > 2 else float("nan")

    wf = walk_forward(M, train, step, fixed_col, benchmark, ann) if T > train + step else {}
    return GateReport(n_trials=N, n_eff=n_eff, mean_corr=mean_corr,
                      pbo=pbo_cscv(M, s_blocks, ann), is_oos_r=r,
                      walkforward=wf, labels=labels,
                      best_label=labels[int(np.nanargmax(s_is))])


# ── 자체 검증: 2026-08-16 크립토 TSM 사례를 재현한다 ────────────────────────
def _demo() -> None:
    import pandas as pd

    PARQUET = "/Users/macbookpro/Desktop/TIDE/data/cache_ohlcv.parquet"
    TICKERS = ["KRW-BTC", "KRW-ETH"]
    FEE, VOL_TARGET, VOL_LB = 0.0005, 0.40, 30      # TIDE origin/main config 정합
    SHORTS = [7, 10, 14, 21, 28, 30, 40, 60]
    LONGS = [14, 21, 28, 30, 45, 60, 90, 120, 180]

    df = pd.read_parquet(PARQUET)
    close = df.xs("close", axis=1, level=1)[TICKERS].astype(float).dropna()
    rets = close.pct_change(fill_method=None).fillna(0.0)
    scale = (VOL_TARGET / (rets.rolling(VOL_LB).std() * sqrt(365))).clip(upper=1.0).fillna(0.0)

    cols, labels = [], []
    for s, l in itertools.product(SHORTS, LONGS):
        if s >= l:
            continue
        sig = ((close.pct_change(s, fill_method=None) > 0).astype(float)
               + (close.pct_change(l, fill_method=None) > 0).astype(float)) / 2.0
        w = (sig * scale / len(TICKERS)).shift(1).fillna(0.0)
        cols.append(((w * rets).sum(axis=1)
                     - (w - w.shift(1).fillna(0.0)).abs().sum(axis=1) * FEE).values)
        labels.append(f"{s}/{l}")

    M = np.array(cols).T
    rep = selection_gate(M, labels, fixed_col=labels.index("30/90"),
                         benchmark=rets.mean(axis=1).values)
    print("크립토 TSM 룩백 — 2026-08-16 사례 재현 (라이브 config 정합)")
    print(f"  기간 {close.index[0].date()}~{close.index[-1].date()} · IS 최적 = {rep.best_label}")
    print()
    print(rep.render())


if __name__ == "__main__":
    _demo()
